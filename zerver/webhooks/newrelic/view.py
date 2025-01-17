# Webhooks for external integrations.
from typing import Any, Dict

from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext as _

from zerver.decorator import webhook_view
from zerver.lib.exceptions import JsonableError
from zerver.lib.request import REQ, has_request_variables
from zerver.lib.response import json_success
from zerver.lib.webhooks.common import check_send_webhook_message, unix_milliseconds_to_timestamp
from zerver.models import UserProfile

# Newrelic planned to upgrade Alert Notification Channels to Workflows and Destinations
# https://discuss.newrelic.com/t/plan-to-upgrade-alert-notification-channels-to-workflows-and-destinations/188205
# This view will handle both old and new format but will keep it easy to delete the old code
# once it is EOLed by the end of June, 2023

# Once old is EOLed, delete the OPEN_TEMPLATE
OPEN_TEMPLATE = """
[Incident]({incident_url}) **opened** for condition: **{condition_name}** at <time:{iso_timestamp}>
``` quote
{details}
```
""".strip()

ACTIVE_TEMPLATE = """
[Incident]({incident_url}) **active** for condition: **{condition_name}** at <time:{iso_timestamp}>
``` quote
{details}
```
""".strip()

DEFAULT_TEMPLATE = (
    """[Incident]({incident_url}) **{status}** {owner}for condition: **{condition_name}**""".strip()
)

TOPIC_TEMPLATE = """{policy_name} ({incident_id})""".strip()

# Once old is EOLed, delete old and keep new
OLD_EVENT_TYPES = ["closed", "acknowledged", "open"]
NEW_EVENT_TYPES = ["created", "activated", "acknowledged", "closed"]
ALL_EVENT_TYPES = list(set(OLD_EVENT_TYPES).union(set(NEW_EVENT_TYPES)))


@webhook_view("NewRelic", all_event_types=ALL_EVENT_TYPES)
@has_request_variables
def api_newrelic_webhook(
    request: HttpRequest,
    user_profile: UserProfile,
    payload: Dict[str, Any] = REQ(argument_type="body"),
) -> HttpResponse:

    # Handle old format
    # Once old is EOLed, delete if block and keep else block
    if not payload.get("id"):
        info = {
            "condition_name": payload.get("condition_name", "Unknown condition"),
            "details": payload.get("details", "No details."),
            "incident_url": payload.get("incident_url", "https://alerts.newrelic.com"),
            "incident_acknowledge_url": payload.get(
                "incident_acknowledge_url", "https://alerts.newrelic.com"
            ),
            "status": payload.get("current_state", "None"),
            "iso_timestamp": "",
            "owner": payload.get("owner", ""),
        }

        unix_time = payload.get("timestamp", None)
        if unix_time is None:
            raise JsonableError(_("The newrelic webhook requires timestamp in milliseconds"))

        info["iso_timestamp"] = unix_milliseconds_to_timestamp(unix_time, "newrelic")

        # Add formatting to the owner field if owner is present
        if info["owner"] != "":
            info["owner"] = "by **{}** ".format(info["owner"])

        # These are the three promised current_state values
        if info["status"].lower() == "open":
            content = OPEN_TEMPLATE.format(**info)
        elif info["status"].lower() == "acknowledged":
            content = DEFAULT_TEMPLATE.format(**info)
        elif info["status"].lower() == "closed":
            content = DEFAULT_TEMPLATE.format(**info)
        else:
            raise JsonableError(
                _("The newrelic webhook requires current_state be in [open|acknowledged|closed]")
            )

        topic_info = {
            "policy_name": payload.get("policy_name", "Unknown Policy"),
            "incident_id": payload.get("incident_id", "Unknown ID"),
        }
        topic = TOPIC_TEMPLATE.format(**topic_info)

        check_send_webhook_message(request, user_profile, topic, content, info["status"])
        return json_success(request)

    # Handle new format
    else:
        info = {
            "condition_name": payload.get("condition_name", "Unknown condition"),
            "details": payload.get("details", "No details."),
            "incident_url": payload.get("issueUrl", "https://alerts.newrelic.com"),
            "incident_acknowledge_url": payload.get(
                "incident_acknowledge_url", "https://alerts.newrelic.com"
            ),
            "status": payload.get("state", "None"),
            "iso_timestamp": "",
            "owner": payload.get("owner", ""),
        }

        unix_time = payload.get("createdAt", None)
        if unix_time is None:
            raise JsonableError(_("The newrelic webhook requires timestamp in milliseconds"))

        info["iso_timestamp"] = unix_milliseconds_to_timestamp(unix_time, "newrelic")

        # Add formatting to the owner field if owner is present
        if info["owner"] != "":
            info["owner"] = "by **{}** ".format(info["owner"])

        # These are the three promised state values
        if info["status"].lower() == "activated":
            content = ACTIVE_TEMPLATE.format(**info)
        elif info["status"].lower() == "acknowledged":
            content = DEFAULT_TEMPLATE.format(**info)
        elif info["status"].lower() == "closed":
            content = DEFAULT_TEMPLATE.format(**info)
        elif info["status"].lower() == "created":
            content = DEFAULT_TEMPLATE.format(**info)
        else:
            raise JsonableError(
                _(
                    "The newrelic webhook requires state be in [created|activated|acknowledged|closed]"
                )
            )

        policy_names_list = payload.get("alertPolicyNames", [])
        if policy_names_list:
            policy_names_str = ",".join(policy_names_list)
        else:
            policy_names_str = "Unknown Policy"
        topic_info = {
            "policy_name": policy_names_str,
            "incident_id": payload.get("id", "Unknown ID"),
        }
        topic = TOPIC_TEMPLATE.format(**topic_info)

        check_send_webhook_message(request, user_profile, topic, content, info["status"])
        return json_success(request)
