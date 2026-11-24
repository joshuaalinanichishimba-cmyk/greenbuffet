# Database documentation

Generated from the models on 24 November 2026: 43 tables. Money columns end in `_ngwee` (whole ngwee). Stock quantities end in `_milli` (thousandths of the ingredient's unit). Times are stored in UTC and shown in Africa/Lusaka time.

The delivery, catering and messages tables and columns were removed in stage 22, after a backup.

## accounts

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| code | varchar(12) | no | unique |
| name | varchar(80) | no |  |
| type | varchar(12) | no |  |
| description | varchar(200) | no |  |
| is_system | boolean | no |  |
| is_active | boolean | no |  |
| is_cash | boolean | no |  |
| sort | integer | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## attendance

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| employee_id | varchar(32) | no | → employees.id |
| day | date | no |  |
| clock_in | timestamp with time zone | no |  |
| clock_out | timestamp with time zone | yes |  |
| note | varchar(160) | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## audit_log

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| at | timestamp with time zone | no |  |
| actor | varchar(80) | no |  |
| area | varchar(40) | no |  |
| action | varchar(80) | no |  |
| detail | varchar(300) | no |  |
| reference | varchar(60) | no |  |
| before | text | yes |  |
| after | text | yes |  |

## cash_movements

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| shift_id | varchar(32) | no | → shifts.id |
| kind | varchar(10) | no |  |
| amount_ngwee | integer | no |  |
| reason | varchar(200) | no |  |
| status | varchar(10) | no |  |
| decided_by | varchar(80) | yes |  |
| decided_at | timestamp with time zone | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## categories

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| name | varchar(60) | no | unique |
| description | varchar(200) | no |  |
| sort | integer | no |  |
| is_active | boolean | no |  |
| earns_stamp | boolean | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## counters

| Column | Type | Null | Notes |
|---|---|---|---|
| key | varchar(40) | no | primary key |
| value | integer | no |  |

## customers

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| phone | varchar(24) | no | unique |
| name | varchar(80) | no |  |
| email | varchar(120) | no |  |
| area | varchar(80) | no |  |
| address | varchar(200) | no |  |
| note | varchar(300) | no |  |
| stamps | integer | no |  |
| orders_count | integer | no |  |
| spent_ngwee | integer | no |  |
| last_order_at | timestamp with time zone | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## documents

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| name | varchar(160) | no |  |
| kind | varchar(16) | no |  |
| attached_to | varchar(16) | no |  |
| attached_id | varchar(32) | yes |  |
| path | varchar(240) | no |  |
| thumb_path | varchar(240) | yes |  |
| media_type | varchar(80) | no |  |
| size_bytes | integer | no |  |
| note | varchar(300) | no |  |
| is_primary | boolean | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## employees

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| number | varchar(16) | no | unique |
| name | varchar(80) | no |  |
| user_id | varchar(32) | yes | unique, → users.id |
| job_title | varchar(60) | no |  |
| department | varchar(40) | no |  |
| phone | varchar(24) | no |  |
| napsa_number | varchar(24) | no |  |
| tpin | varchar(16) | no |  |
| pay_method | varchar(16) | no |  |
| pay_account | varchar(40) | no |  |
| basic_ngwee | integer | no |  |
| allowances_ngwee | integer | no |  |
| leave_days_per_year | integer | no |  |
| start_date | date | yes |  |
| is_active | boolean | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## feedback

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| order_id | varchar(32) | yes | → orders.id |
| order_number | varchar(24) | no |  |
| rating | integer | no |  |
| comment | varchar(500) | no |  |
| source | varchar(12) | no |  |
| customer_name | varchar(80) | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## idempotency_keys

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| key | varchar(80) | no |  |
| scope | varchar(40) | no |  |
| result_id | varchar(32) | no |  |
| detail | text | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## ingredients

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| name | varchar(80) | no | unique |
| unit | varchar(8) | no |  |
| cost_ngwee | integer | no |  |
| is_active | boolean | no |  |
| note | varchar(200) | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## journal_entries

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| number | varchar(24) | no | unique |
| entry_date | date | no |  |
| memo | varchar(300) | no |  |
| source | varchar(16) | no |  |
| reference | varchar(40) | no |  |
| status | varchar(12) | no |  |
| posted_at | timestamp with time zone | yes |  |
| posted_by | varchar(80) | yes |  |
| approved_at | timestamp with time zone | yes |  |
| approved_by | varchar(80) | yes |  |
| reverses_id | varchar(32) | yes | → journal_entries.id |
| reversed_by_id | varchar(32) | yes |  |
| note | text | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## journal_lines

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| entry_id | varchar(32) | no | → journal_entries.id |
| account_id | varchar(32) | no | → accounts.id |
| position | integer | no |  |
| debit_ngwee | integer | no |  |
| credit_ngwee | integer | no |  |
| memo | varchar(200) | no |  |

## kitchen_items

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| order_id | varchar(32) | no | → orders.id |
| order_line_id | varchar(32) | no | → order_lines.id |
| order_number | varchar(24) | no |  |
| product_name | varchar(90) | no |  |
| quantity | integer | no |  |
| choices | varchar(300) | no |  |
| note | varchar(160) | no |  |
| station | varchar(24) | no |  |
| order_type | varchar(16) | no |  |
| customer_name | varchar(80) | no |  |
| status | varchar(16) | no |  |
| started_at | timestamp with time zone | yes |  |
| ready_at | timestamp with time zone | yes |  |
| served_at | timestamp with time zone | yes |  |
| handled_by | varchar(80) | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## leave_requests

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| employee_id | varchar(32) | no | → employees.id |
| kind | varchar(16) | no |  |
| start | date | no |  |
| end | date | no |  |
| days | integer | no |  |
| reason | varchar(200) | no |  |
| status | varchar(12) | no |  |
| decided_by | varchar(80) | yes |  |
| decided_at | timestamp with time zone | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## login_attempts

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| email | varchar(120) | no |  |
| at | timestamp with time zone | no |  |
| succeeded | boolean | no |  |
| ip | varchar(60) | no |  |

## option_groups

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| name | varchar(60) | no | unique |
| helper | varchar(160) | no |  |
| min_select | integer | no |  |
| max_select | integer | no |  |
| free_count | integer | no |  |
| extra_ngwee | integer | no |  |
| is_active | boolean | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## option_items

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| group_id | varchar(32) | no | → option_groups.id |
| name | varchar(60) | no |  |
| price_ngwee | integer | no |  |
| is_active | boolean | no |  |
| is_available | boolean | no |  |
| sort | integer | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## order_line_options

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| line_id | varchar(32) | no | → order_lines.id |
| option_item_id | varchar(32) | no | → option_items.id |
| group_name | varchar(60) | no |  |
| item_name | varchar(60) | no |  |
| price_ngwee | integer | no |  |

## order_lines

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| order_id | varchar(32) | no | → orders.id |
| position | integer | no |  |
| product_id | varchar(32) | no | → products.id |
| product_name | varchar(90) | no |  |
| product_code | varchar(24) | no |  |
| station | varchar(24) | no |  |
| unit_ngwee | integer | no |  |
| options_ngwee | integer | no |  |
| quantity | integer | no |  |
| line_ngwee | integer | no |  |
| vat_rate | integer | no |  |
| note | varchar(160) | no |  |

## orders

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| number | varchar(24) | no | unique |
| shift_id | varchar(32) | yes | → shifts.id |
| order_type | varchar(16) | no |  |
| status | varchar(16) | no |  |
| customer_name | varchar(80) | no |  |
| customer_phone | varchar(24) | no |  |
| note | varchar(300) | no |  |
| customer_id | varchar(32) | yes | → customers.id |
| stamps_earned | integer | no |  |
| stamps_redeemed | integer | no |  |
| free_item_ngwee | integer | no |  |
| promo_code | varchar(24) | no |  |
| promo_ngwee | integer | no |  |
| discount_reason | varchar(160) | no |  |
| discount_approved_by | varchar(80) | yes |  |
| subtotal_ngwee | integer | no |  |
| discount_ngwee | integer | no |  |
| total_ngwee | integer | no |  |
| vat_ngwee | integer | no |  |
| paid_at | timestamp with time zone | yes |  |
| cancelled_at | timestamp with time zone | yes |  |
| cancelled_by | varchar(80) | yes |  |
| cancel_reason | varchar(300) | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## payments

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| order_id | varchar(32) | no | → orders.id |
| shift_id | varchar(32) | yes | → shifts.id |
| method | varchar(16) | no |  |
| amount_ngwee | integer | no |  |
| tendered_ngwee | integer | yes |  |
| change_ngwee | integer | yes |  |
| reference | varchar(60) | no |  |
| is_refund | boolean | no |  |
| note | varchar(200) | no |  |
| status | varchar(12) | no |  |
| confirmed_by | varchar(80) | yes |  |
| confirmed_at | timestamp with time zone | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## payroll_runs

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| period | varchar(7) | no | unique |
| status | varchar(12) | no |  |
| gross_ngwee | integer | no |  |
| net_ngwee | integer | no |  |
| paye_ngwee | integer | no |  |
| napsa_ngwee | integer | no |  |
| nhima_ngwee | integer | no |  |
| employer_cost_ngwee | integer | no |  |
| rates_used | varchar(2000) | no |  |
| approved_by | varchar(80) | yes |  |
| approved_at | timestamp with time zone | yes |  |
| paid_by | varchar(80) | yes |  |
| paid_at | timestamp with time zone | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## payslips

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| run_id | varchar(32) | no | → payroll_runs.id |
| employee_id | varchar(32) | no | → employees.id |
| employee_name | varchar(80) | no |  |
| employee_number | varchar(16) | no |  |
| job_title | varchar(60) | no |  |
| napsa_number | varchar(24) | no |  |
| tpin | varchar(16) | no |  |
| basic_ngwee | integer | no |  |
| allowances_ngwee | integer | no |  |
| unpaid_days | integer | no |  |
| unpaid_deduction_ngwee | integer | no |  |
| gross_ngwee | integer | no |  |
| paye_ngwee | integer | no |  |
| napsa_employee_ngwee | integer | no |  |
| napsa_employer_ngwee | integer | no |  |
| nhima_employee_ngwee | integer | no |  |
| nhima_employer_ngwee | integer | no |  |
| net_ngwee | integer | no |  |
| days_worked | integer | no |  |

## permissions

| Column | Type | Null | Notes |
|---|---|---|---|
| code | varchar(40) | no | primary key |
| label | varchar(80) | no |  |
| area | varchar(40) | no |  |
| sort | integer | no |  |

## points_entries

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| customer_id | varchar(32) | no | → customers.id |
| order_id | varchar(32) | yes | → orders.id |
| points | integer | no |  |
| balance_after | integer | no |  |
| reason | varchar(120) | no |  |
| created_by | varchar(80) | yes |  |
| created_at | timestamp with time zone | no |  |

## price_changes

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| product_id | varchar(32) | no | → products.id |
| old_ngwee | integer | no |  |
| new_ngwee | integer | no |  |
| reason | text | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## product_option_groups

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| product_id | varchar(32) | no | → products.id |
| group_id | varchar(32) | no | → option_groups.id |
| sort | integer | no |  |

## products

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| code | varchar(24) | no | unique |
| name | varchar(90) | no |  |
| description | varchar(300) | no |  |
| category_id | varchar(32) | no | → categories.id |
| price_ngwee | integer | no |  |
| vat_rate | numeric(5, 2) | no |  |
| station | varchar(24) | no |  |
| is_active | boolean | no |  |
| is_available | boolean | no |  |
| sort | integer | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## promotions

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| code | varchar(24) | no | unique |
| label | varchar(120) | no |  |
| kind | varchar(10) | no |  |
| value | integer | no |  |
| minimum_ngwee | integer | no |  |
| is_active | boolean | no |  |
| uses | integer | no |  |
| discount_given_ngwee | integer | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## purchase_lines

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| purchase_id | varchar(32) | no | → purchases.id |
| ingredient_id | varchar(32) | no | → ingredients.id |
| ingredient_name | varchar(80) | no |  |
| unit | varchar(8) | no |  |
| quantity_milli | integer | no |  |
| unit_cost_ngwee | integer | no |  |
| line_ngwee | integer | no |  |

## purchases

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| number | varchar(24) | no | unique |
| supplier_id | varchar(32) | no | → suppliers.id |
| status | varchar(16) | no |  |
| invoice_number | varchar(40) | no |  |
| note | varchar(300) | no |  |
| total_ngwee | integer | no |  |
| received_at | timestamp with time zone | yes |  |
| received_by | varchar(80) | yes |  |
| cancelled_at | timestamp with time zone | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## recipe_lines

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| product_id | varchar(32) | yes | → products.id |
| option_item_id | varchar(32) | yes | → option_items.id |
| ingredient_id | varchar(32) | no | → ingredients.id |
| quantity_milli | integer | no |  |
| note | varchar(120) | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## role_permissions

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| role_id | varchar(40) | no | → roles.id |
| permission_code | varchar(40) | no | → permissions.code |

## roles

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(40) | no | primary key |
| label | varchar(60) | no |  |
| description | varchar(200) | no |  |
| is_system | boolean | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## settings

| Column | Type | Null | Notes |
|---|---|---|---|
| key | varchar(60) | no | primary key |
| value | text | no |  |
| label | varchar(120) | no |  |

## shifts

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| opened_by | varchar(80) | no |  |
| opened_by_id | varchar(32) | no | → users.id |
| opened_at | timestamp with time zone | no |  |
| float_ngwee | integer | no |  |
| closed_at | timestamp with time zone | yes |  |
| closed_by | varchar(80) | yes |  |
| expected_ngwee | integer | yes |  |
| counted_ngwee | integer | yes |  |
| variance_ngwee | integer | yes |  |
| note | varchar(300) | no |  |
| first_count_ngwee | integer | yes |  |
| reviewed_by | varchar(80) | yes |  |
| reviewed_at | timestamp with time zone | yes |  |
| review_note | varchar(300) | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## stock_levels

| Column | Type | Null | Notes |
|---|---|---|---|
| ingredient_id | varchar(32) | no | primary key, → ingredients.id |
| quantity_milli | integer | no |  |
| reorder_milli | integer | no |  |
| updated_at | timestamp with time zone | yes |  |

## stock_moves

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| ingredient_id | varchar(32) | no | → ingredients.id |
| kind | varchar(16) | no |  |
| quantity_milli | integer | no |  |
| value_ngwee | integer | no |  |
| reference | varchar(40) | no |  |
| note | varchar(200) | no |  |
| balance_milli | integer | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## supplier_payments

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| purchase_id | varchar(32) | no | → purchases.id |
| supplier_id | varchar(32) | no | → suppliers.id |
| method | varchar(16) | no |  |
| amount_ngwee | integer | no |  |
| reference | varchar(60) | no |  |
| note | varchar(200) | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## suppliers

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| name | varchar(80) | no | unique |
| contact | varchar(80) | no |  |
| phone | varchar(24) | no |  |
| email | varchar(120) | no |  |
| note | varchar(300) | no |  |
| is_active | boolean | no |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |

## users

| Column | Type | Null | Notes |
|---|---|---|---|
| id | varchar(32) | no | primary key |
| name | varchar(80) | no |  |
| email | varchar(120) | no | unique |
| password_hash | varchar(255) | no |  |
| role_id | varchar(40) | no | → roles.id |
| is_active | boolean | no |  |
| must_change_password | boolean | no |  |
| token_version | integer | no |  |
| last_login_at | timestamp with time zone | yes |  |
| created_at | timestamp with time zone | no |  |
| created_by | varchar(80) | yes |  |
