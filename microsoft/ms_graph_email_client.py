from typing import List, Dict, Optional, Any
import requests
import msal
from bs4 import BeautifulSoup
import re


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class MicrosoftGraphEmailClient:
    """
    Microsoft Graph Email Client using client credentials flow.
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

    def fetch_messages(
        self,
        user_email: str,
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
            Target mailbox email.
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

        url = (
            f"{GRAPH_BASE_URL}/users/{user_email}/messages"
            f"?$filter={filter_query}"
            f"&$select={select_query}"
            f"&$top={page_size}"
        )

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

            messages.extend(
                self._normalize_message(msg, strip_html=strip_html)
                for msg in data.get("value", [])
            )

            url = data.get("@odata.nextLink")
            page_count += 1

            if max_pages and page_count >= max_pages:
                break

        return messages

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