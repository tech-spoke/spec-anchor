# Checkout Service Spec

## Order Approval Policy

The checkout service MUST require manager approval for every order whose total
is above 1000 USD. Such an order is held in a pending state and is never
shipped until a human manager explicitly approves it. Automatic approval of
high-value orders is forbidden. (E2E edit: clarified that this rule applies to all storefront channels.)

## Refund Window

The checkout service MUST allow a refund only within 14 days of the original
purchase. After the 14-day window has elapsed, the service MUST reject the
refund request. There is no exception to this deadline.
