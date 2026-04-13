## Task 128

### Context

- support bot admin queue could render a very long inline keyboard;
- the users surface did not expose whether a user is subscribed to the public channel;
- `/start` in `@amonora_bot` could still hard-block first-time trial activation behind a channel check;
- the request also required a safe small optimization pass without risky architecture changes.

### Scope

- cap support-bot admin ticket list to a short operational slice;
- add a safe channel-subscription signal to the users control-center surface;
- ensure first `/start` activates trial immediately;
- apply only bounded, reversible optimizations.

### Constraints

- do not break active users or current payment/access flows;
- do not add dangerous migrations;
- do not turn Telegram API health into a hard dependency for the dashboard;
- keep fixes small and reversible.

### Acceptance

- support bot admin list shows no more than 5 ticket buttons;
- users payload/detail exposes `subscribed / not_subscribed / unknown`;
- first-time `/start` grants trial without a channel gate;
- tests cover the changed seams.
