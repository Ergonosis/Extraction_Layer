from typing import List, Dict, Optional, Any
import requests
import msal
from bs4 import BeautifulSoup
import re


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class MicrosoftGraphEmailClient:
    """
    Microsoft Graph data client.

    Supports:
    - Client credentials (app-only) via __init__ — used by microsoft/usage.py
    - Delegated access token via from_access_token — used by the portal API
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        timeout: int = 30,
    ) -> None:
        self._authority = f"https://login.microsoftonline.com/{tenant_id}"
        self._timeout = timeout

        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=self._authority,
            client_credential=client_secret,
        )

        self._access_token = self._acquire_token()

    @classmethod
    def from_access_token(
        cls,
        access_token: str,
        timeout: int = 30,
    ) -> "MicrosoftGraphEmailClient":
        """Build a client that uses an existing delegated (or app) access token."""
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("access_token is required")
        obj = cls.__new__(cls)
        obj._timeout = timeout
        obj._app = None
        obj._access_token = access_token.strip()
        return obj

    def _acquire_token(self) -> str:
        result = self._app.acquire_token_for_client(scopes=GRAPH_SCOPE)

        if "access_token" not in result:
            raise RuntimeError(
                f"Failed to acquire token: {result.get('error_description')}"
            )

        return result["access_token"]

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def _messages_url(self, user_email: Optional[str], query: str) -> str:
        mailbox = (user_email or "").strip()
        if not mailbox or mailbox.lower() == "me":
            return f"{GRAPH_BASE_URL}/me/messages?{query}"
        return f"{GRAPH_BASE_URL}/users/{mailbox}/messages?{query}"

    def fetch_profile(self) -> Dict[str, Any]:
        """Fetch the signed-in user's basic profile (User.Read / GET /me)."""
        response = requests.get(
            f"{GRAPH_BASE_URL}/me",
            headers=self._headers,
            params={
                "$select": "id,displayName,mail,userPrincipalName,jobTitle",
            },
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Graph API error {response.status_code}: {response.text}"
            )
        data = response.json()
        return {
            "id": data.get("id"),
            "display_name": data.get("displayName"),
            "mail": data.get("mail"),
            "user_principal_name": data.get("userPrincipalName"),
            "job_title": data.get("jobTitle"),
        }

    def fetch_messages(
        self,
        user_email: Optional[str],
        start_datetime: str,
        end_datetime: str,
        select_fields: Optional[List[str]] = None,
        page_size: int = 50,
        max_pages: Optional[int] = None,
        strip_html: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch messages for a user within a datetime range.

        Parameters
        ----------
        user_email : str
            Target mailbox email, or ``me`` / empty for delegated /me/messages.
        start_datetime : str
            ISO 8601 UTC string (e.g. '2026-01-01T00:00:00Z').
        end_datetime : str
            ISO 8601 UTC string.
        select_fields : list[str], optional
            Fields to retrieve from Graph API.
        page_size : int
            Messages per page.
        max_pages : int, optional
            Limit number of pages fetched.
        strip_html : bool
            If True, converts HTML bodies to clean plain text.
            If False, returns raw body content.

        Returns
        -------
        List[Dict[str, Any]]
        """

        if select_fields is None:
            select_fields = [
                "subject",
                "from",
                "toRecipients",
                "receivedDateTime",
                "body",
            ]

        filter_query = (
            f"receivedDateTime ge {start_datetime} and "
            f"receivedDateTime le {end_datetime}"
        )

        select_query = ",".join(select_fields)
        query = f"$filter={filter_query}&$select={select_query}&$top={page_size}"
        url = self._messages_url(user_email, query)

        messages: List[Dict[str, Any]] = []
        page_count = 0

        while url:
            response = requests.get(
                url,
                headers=self._headers,
                timeout=self._timeout,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Graph API error {response.status_code}: {response.text}"
                )

            data = response.json()

            for msg in data.get("value", []):
                messages.append(
                    self._normalize_message(msg, strip_html=strip_html)
                )

            url = data.get("@odata.nextLink")
            page_count += 1

            if max_pages and page_count >= max_pages:
                break

        return messages

    def fetch_events(
        self,
        start_datetime: str,
        end_datetime: str,
        select_fields: Optional[List[str]] = None,
        page_size: int = 50,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch calendar events for the signed-in user (Calendars.Read)."""
        if select_fields is None:
            select_fields = [
                "subject",
                "start",
                "end",
                "organizer",
                "location",
                "isAllDay",
            ]

        params = {
            "startDateTime": start_datetime,
            "endDateTime": end_datetime,
            "$select": ",".join(select_fields),
            "$top": str(page_size),
        }
        url: Optional[str] = f"{GRAPH_BASE_URL}/me/calendarView"
        events: List[Dict[str, Any]] = []
        page_count = 0
        first = True

        while url:
            response = requests.get(
                url,
                headers={
                    **self._headers,
                    "Prefer": 'outlook.timezone="UTC"',
                },
                params=params if first else None,
                timeout=self._timeout,
            )
            first = False

            if response.status_code != 200:
                raise RuntimeError(
                    f"Graph API error {response.status_code}: {response.text}"
                )

            data = response.json()
            for event in data.get("value", []):
                events.append(self._normalize_event(event))

            url = data.get("@odata.nextLink")
            page_count += 1
            if max_pages and page_count >= max_pages:
                break

        return events

    @staticmethod
    def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
        organizer = (
            event.get("organizer", {})
            .get("emailAddress", {})
            .get("address")
        )
        location = event.get("location") or {}
        return {
            "subject": event.get("subject"),
            "start": event.get("start"),
            "end": event.get("end"),
            "organizer": organizer,
            "location": location.get("displayName"),
            "is_all_day": event.get("isAllDay"),
        }

    @staticmethod
    def _normalize_message(
        msg: Dict[str, Any],
        strip_html: bool = True,
    ) -> Dict[str, Any]:
        """
        Normalize Graph API message to structured dictionary.
        """

        body = msg.get("body", {})
        content = body.get("content", "")

        if strip_html and body.get("contentType") == "html":
            content = MicrosoftGraphEmailClient._html_to_text(content)

        return {
            "subject": msg.get("subject"),
            "from": msg.get("from", {})
            .get("emailAddress", {})
            .get("address"),
            "to": [
                r.get("emailAddress", {}).get("address")
                for r in msg.get("toRecipients", [])
            ],
            "received_datetime": msg.get("receivedDateTime"),
            "body": content,
            "body_content_type": body.get("contentType"),
        }

    @staticmethod
    def _html_to_text(html: str):
        """
        Extract visible text from HTML email body.
        Returns only human-readable content.
        """

        if not html:
            return ""

        soup = BeautifulSoup(html, "lxml")
        # Get body content only (ignore head completely)
        body = soup.body

        if body:
            text = body.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        return text


def fetch_user_emails(
    client_id: str,
    client_secret: str,
    tenant_id: str,
    user_email: str,
    start_datetime: str,
    end_datetime: str,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Public convenience wrapper for single-function usage.
    """

    client = MicrosoftGraphEmailClient(
        client_id=client_id,
        client_secret=client_secret,
        tenant_id=tenant_id,
    )

    return client.fetch_messages(
        user_email=user_email,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        **kwargs,
    )