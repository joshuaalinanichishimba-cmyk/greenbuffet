"""The kitchen display.

Orders reach the board the moment they are paid. The board itself is a plain
list the kitchen can read at arm's length; it refreshes over a WebSocket when
one is available, and falls back to asking again every few seconds when it is
not, because a kitchen screen that silently stops updating is worse than one
that is a little slow.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.permissions import requires
from app.core.security import decode_token
from app.models.access import User
from app.models.kitchen import NEXT_STATUS, STATIONS, STATUSES, KitchenItem
from app.models.sales import Order
from app.services.audit import record

router = APIRouter(prefix="/kitchen", tags=["kitchen"])

can_see = requires("kitchen.view", "orders.view", "pos.use")
can_work = requires("kitchen.view", "orders.update")

STATION_LABELS = {"kitchen": "Kitchen", "cold": "Cold station", "bar": "Juice bar"}


class StatusIn(BaseModel):
    status: str = Field(min_length=3, max_length=16)


class ItemOut(BaseModel):
    id: str
    product_name: str
    quantity: int
    choices: str
    note: str
    station: str
    station_label: str
    status: str
    handled_by: str | None


class TicketOut(BaseModel):
    order_id: str
    order_number: str
    order_type: str
    customer_name: str
    placed_at: str
    waiting_minutes: int
    status: str
    items: list[ItemOut]


# ---------------------------------------------------------------------------
# Live updates
# ---------------------------------------------------------------------------

class Board:
    """Everyone currently watching the board, so a change reaches them all."""

    def __init__(self) -> None:
        self._watchers: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def join(self, socket: WebSocket) -> None:
        async with self._lock:
            self._watchers.add(socket)

    async def leave(self, socket: WebSocket) -> None:
        async with self._lock:
            self._watchers.discard(socket)

    async def tell_everyone(self, message: dict) -> None:
        async with self._lock:
            watchers = list(self._watchers)
        for socket in watchers:
            try:
                await socket.send_text(json.dumps(message))
            except Exception:
                # A closed tab should never stop the kitchen hearing about an order.
                await self.leave(socket)


board = Board()


# The server's own event loop, remembered the first time a board connects.
#
# Most routes here are plain functions, which FastAPI runs on a worker thread.
# A worker thread has no event loop of its own, so the old version of
# announce() found none and silently did nothing: every "new order" message
# was dropped, and boards only caught up through their slow poll. A thread
# cannot use the loop directly, but it can hand it work, which is what
# run_coroutine_threadsafe is for.
_server_loop: asyncio.AbstractEventLoop | None = None


def announce(event: str, detail: dict | None = None) -> None:
    """Tells the open boards something changed, without blocking the request."""
    message = {"event": event, **(detail or {})}
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.create_task(board.tell_everyone(message))
        return
    if _server_loop is not None and _server_loop.is_running():
        asyncio.run_coroutine_threadsafe(board.tell_everyone(message), _server_loop)
    # No loop yet means no board has ever connected, so nobody is listening.


def send_to_kitchen(db: Session, order: Order) -> int:
    """Puts a paid order's lines on the board. Called when payment completes."""
    already = db.scalar(select(KitchenItem).where(KitchenItem.order_id == order.id))
    if already:
        return 0
    made = 0
    for line in order.lines:
        # Choices are kept by group - "Base: Brown rice | Toppings: Avocado,
        # Tomato" - because a cook reads a bowl as base, then protein, then
        # toppings, and the prep list adds them up the same way.
        grouped: dict[str, list[str]] = {}
        for option in line.options:
            grouped.setdefault(option.group_name, []).append(option.item_name)
        choices = " | ".join(f"{group}: {', '.join(names)}" for group, names in grouped.items())
        db.add(KitchenItem(
            order_id=order.id, order_line_id=line.id, order_number=order.number,
            product_name=line.product_name, quantity=line.quantity,
            choices=choices[:300],
            note=line.note, station=line.station, order_type=order.order_type,
            customer_name=order.customer_name, created_by=order.created_by,
        ))
        made += 1
    return made


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------

def _item_out(item: KitchenItem) -> ItemOut:
    return ItemOut(
        id=item.id, product_name=item.product_name, quantity=item.quantity,
        choices=item.choices, note=item.note, station=item.station,
        station_label=STATION_LABELS.get(item.station, item.station),
        status=item.status, handled_by=item.handled_by,
    )


def _tickets(items: list[KitchenItem]) -> list[TicketOut]:
    now = datetime.now(timezone.utc)
    grouped: dict[str, list[KitchenItem]] = {}
    for item in items:
        grouped.setdefault(item.order_id, []).append(item)

    tickets: list[TicketOut] = []
    for order_id, lines in grouped.items():
        first = lines[0]
        # A ticket is only as far along as its least finished item.
        rank = {"waiting": 0, "preparing": 1, "ready": 2, "served": 3}
        overall = min(lines, key=lambda i: rank[i.status]).status
        placed = min(i.created_at for i in lines)
        tickets.append(TicketOut(
            order_id=order_id, order_number=first.order_number,
            order_type=first.order_type, customer_name=first.customer_name,
            placed_at=placed.isoformat(),
            waiting_minutes=int((now - placed).total_seconds() // 60),
            status=overall,
            items=[_item_out(i) for i in lines],
        ))
    # Oldest first: the kitchen works down the list.
    tickets.sort(key=lambda t: t.placed_at)
    return tickets


@router.get("/tickets", response_model=list[TicketOut])
def tickets(
    station: str | None = Query(default=None),
    include_served: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(can_see),
):
    # The trading day only. A ticket nobody cleared yesterday is not food
    # anyone is waiting for; left on the wall it buries today's orders under
    # timers counting into the hundreds of minutes. It is still in the
    # database, and still on the Orders screen under Last 14 days.
    lusaka = timezone(timedelta(hours=2))
    day_start = datetime.combine(datetime.now(lusaka).date(), datetime.min.time(), tzinfo=lusaka)
    stmt = select(KitchenItem).where(KitchenItem.created_at >= day_start).order_by(KitchenItem.created_at)
    if station:
        if station not in STATIONS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown station.")
        stmt = stmt.where(KitchenItem.station == station)
    if not include_served:
        stmt = stmt.where(KitchenItem.status != "served")
    return _tickets(list(db.scalars(stmt).all()))


def _advance(item: KitchenItem, wanted: str, who: str) -> None:
    now = datetime.now(timezone.utc)
    item.status = wanted
    item.handled_by = who
    if wanted == "preparing" and not item.started_at:
        item.started_at = now
    if wanted == "ready" and not item.ready_at:
        item.ready_at = now
    if wanted == "served" and not item.served_at:
        item.served_at = now


@router.post("/items/{item_id}/status", response_model=list[TicketOut])
def set_item_status(
    item_id: str, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(can_work),
):
    item = db.get(KitchenItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That item is no longer on the board.")
    wanted = body.status.strip().lower()
    if wanted not in STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown step.")
    _advance(item, wanted, user.name)
    db.commit()
    announce("item", {"order_number": item.order_number, "status": wanted})
    return tickets(station=None, include_served=False, db=db, _=user)


@router.post("/tickets/{order_id}/status", response_model=list[TicketOut])
def set_ticket_status(
    order_id: str, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(can_work),
):
    """Moves a whole ticket along, which is what a cook actually taps."""
    items = db.scalars(select(KitchenItem).where(KitchenItem.order_id == order_id)).all()
    if not items:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That ticket is no longer on the board.")
    wanted = body.status.strip().lower()
    if wanted not in STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown step.")
    for item in items:
        _advance(item, wanted, user.name)
    if wanted in ("ready", "served"):
        record(db, user.name, "sales", f"Order {wanted}", items[0].order_number, items[0].order_number)
    db.commit()
    announce("ticket", {"order_number": items[0].order_number, "status": wanted})
    return tickets(station=None, include_served=False, db=db, _=user)


# One step back, for the wrong button pressed. Each step clears the time it
# recorded, so a ticket sent back to "preparing" and finished later is timed
# from when it was really ready, and the kitchen's average stays honest.
PREVIOUS_STATUS = {"preparing": "waiting", "ready": "preparing", "served": "ready"}


@router.post("/tickets/{order_id}/back", response_model=list[TicketOut])
def ticket_back(order_id: str, db: Session = Depends(get_db), user: User = Depends(can_work)):
    """Moves a whole ticket back one step, and says so in the activity log."""
    items = db.scalars(select(KitchenItem).where(KitchenItem.order_id == order_id)).all()
    if not items:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That ticket is no longer on the board.")
    # The ticket is as far along as its least finished item.
    order_of = {name: i for i, name in enumerate(STATUSES)}
    current = min((i.status for i in items), key=lambda s: order_of.get(s, 0))
    back_to = PREVIOUS_STATUS.get(current)
    if not back_to:
        raise HTTPException(status.HTTP_409_CONFLICT, "That ticket has not been started; there is no step to undo.")
    for item in items:
        if item.status != current:
            continue
        item.status = back_to
        item.handled_by = user.name
        if current == "preparing":
            item.started_at = None
        elif current == "ready":
            item.ready_at = None
        elif current == "served":
            item.served_at = None
    record(db, user.name, "sales", "Kitchen step undone",
           f"{items[0].order_number}: {current} back to {back_to}", items[0].order_number)
    db.commit()
    announce("ticket", {"order_number": items[0].order_number, "status": back_to})
    return tickets(station=None, include_served=False, db=db, _=user)


@router.get("/next-step/{current}")
def next_step(current: str, _: User = Depends(can_see)):
    """What tapping a ticket does from where it is now."""
    return {"next": NEXT_STATUS.get(current)}


@router.websocket("/ws")
async def watch(socket: WebSocket, token: str = Query(default="")):
    """Live updates for an open board.

    The token comes as a query parameter because a browser cannot set headers
    on a WebSocket. It is checked the same way as any other request, and the
    socket is closed if it does not belong to someone allowed to see orders.
    """
    global _server_loop
    _server_loop = asyncio.get_running_loop()
    claims = decode_token(token) if token else None
    if not claims:
        await socket.close(code=4401)
        return
    db = SessionLocal()
    try:
        user = db.get(User, claims.get("sub", ""))
        allowed = user and user.is_active and (
            {"kitchen.view", "orders.view", "pos.use"} & set(user.role.permission_codes)
        )
        if not allowed:
            await socket.close(code=4403)
            return
    finally:
        db.close()

    await socket.accept()
    await board.join(socket)
    try:
        await socket.send_text(json.dumps({"event": "ready"}))
        while True:
            # Nothing is expected from the browser; this keeps the socket open
            # and notices when the tab goes away.
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await board.leave(socket)
