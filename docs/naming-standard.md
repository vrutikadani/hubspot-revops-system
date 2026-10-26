# Workflow naming standard

With hundreds of workflows, a name has to tell you what a workflow touches before you open it.

**Format:** `TEAM_[TYPE_]What it does (Version date)`

| Prefix | Owns | Examples |
|---|---|---|
| `OPS_` | Data quality, routing, lifecycle, syncs between objects | `OPS_Contact Assignment (Oct 2026)`, `OPS_ZIP Autofill - Deals` |
| `SALES_` | Deal stages, approvals, deal notifications | `SALES_APPROVAL_2 Device Price - VP Approval` |
| `SERVICE_` | Ticket status, reminders, ERP fields on tickets | `SERVICE_NOTIFY_On Hold_7 Day Reminder` |
| `LEADS_` | Campaign and event lead handling | `LEADS_Webinar_Template` |
| `CS_` | Customer success follow-ups | `CS_NOTIFY_Same Deal Stage_7 Day Reminder` |

| Type tag | Meaning |
|---|---|
| `NOTIFY_` | Only sends emails or tasks, changes no data |
| `CP_` | Copies a property from one object or field to another |
| `APPROVAL_n` | Step *n* of a multi-workflow approval chain |

**Rules**

- Put a version date on any workflow that gets rebuilt. The old one is turned off, not edited in place.
- The description field says the trigger, the main branches and the cutoff date, in one paragraph.
- No people's names in workflow names. Routing branches may name a territory, never a person on a temp basis.
- One-off campaign workflows (events, webinars) are turned off after the event and kept in a dated folder.
