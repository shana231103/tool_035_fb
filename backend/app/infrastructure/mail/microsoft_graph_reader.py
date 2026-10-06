# File: backend/app/infrastructure/mail/microsoft_graph_reader.py
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_code_reader import IMailboxCodeReader
from app.domain.value_objects.mailbox_verification import (
    CandidatePage, CodeCandidate, MailBaseline, MailboxBinding, MailboxMapping, MessageRef, ReadBudget, SendEpoch,
)
from .graph_transport import GRAPH_ROOT

METADATA = "id,internetMessageId,receivedDateTime,from,sender,subject,toRecipients"


class MicrosoftGraphCodeReader(IMailboxCodeReader):
    def __init__(self, transport, parser, *, lookback_seconds=600, page_size=50, max_pages=5):
        if lookback_seconds <= 0 or not 1 <= page_size <= 50 or max_pages <= 0:
            raise ValueError("Invalid Graph scan limits")
        self.transport, self.parser = transport, parser
        self.lookback_seconds, self.page_size, self.max_pages = lookback_seconds, page_size, max_pages

    async def baseline(self, binding: MailboxBinding, budget: ReadBudget) -> MailBaseline:
        captured = datetime.now(timezone.utc)
        ids = set()
        budget.page_remaining = min(budget.page_remaining, self.max_pages)
        # Caller resets scan pages; requests/body budget is never recreated here.
        for folder in binding.folder_refs:
            url = self._list_url(folder, captured - timedelta(seconds=self.lookback_seconds))
            while url:
                budget.consume_page()
                result = await self.transport.get(binding, url, budget.deadline, budget)
                for metadata in self._messages(result):
                    self._ref(metadata, False, False)
                    ids.add(metadata["id"])
                url = result.get("@odata.nextLink")
        return MailBaseline(frozenset(ids), captured, True)

    async def list_candidates(self, epoch: SendEpoch, cursor: str | None, budget: ReadBudget) -> CandidatePage:
        binding = epoch.binding
        if cursor is None:
            folder_index, url = 0, self._list_url(binding.folder_refs[0], epoch.request_started_at)
        else:
            try:
                state = json.loads(cursor)
                folder_index, url = state["folder"], state["url"]
                if (state["epoch"] != epoch.epoch_id or type(folder_index) is not int or
                        not 0 <= folder_index < len(binding.folder_refs)):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise MailboxError("GRAPH_LINK_REJECTED") from None
        self.transport._validate_url(url)
        budget.page_remaining = min(budget.page_remaining, self.max_pages)
        budget.consume_page()
        result = await self.transport.get(binding, url, epoch.deadline, budget)
        mapping = MailboxMapping(binding.meta_email, binding.meta_email, folders=binding.folder_refs,
                                 template_version=binding.template_version)
        refs = []
        for metadata in self._messages(result):
            ref = self._ref(metadata, True, True)
            if ref.id not in epoch.baseline_ids and self.parser.metadata_matches(metadata, mapping):
                refs.append(ref)
        url = result.get("@odata.nextLink")
        if not url and folder_index + 1 < len(binding.folder_refs):
            folder_index += 1
            url = self._list_url(binding.folder_refs[folder_index], epoch.request_started_at)
        next_cursor = json.dumps({"epoch": epoch.epoch_id, "folder": folder_index, "url": url}) if url else None
        return CandidatePage(tuple(refs), next_cursor, not bool(next_cursor))

    async def read_candidate(self, binding: MailboxBinding, ref: MessageRef, budget: ReadBudget) -> CodeCandidate | None:
        budget.consume_body()
        url = GRAPH_ROOT + "/me/messages/" + quote(ref.id, safe="") + "?" + urlencode({"$select": METADATA + ",body"})
        metadata = await self.transport.get(binding, url, budget.deadline, budget)
        fresh = self._ref(metadata, True, True)
        if (fresh.id != ref.id or fresh.internet_message_id != ref.internet_message_id or
                fresh.received_at != ref.received_at):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        mapping = MailboxMapping(binding.meta_email, binding.meta_email, folders=binding.folder_refs,
                                 template_version=binding.template_version)
        if not self.parser.metadata_matches(metadata, mapping):
            return None
        body = metadata.get("body", {})
        if not isinstance(body, dict):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        candidate = self.parser.parse(metadata, body.get("content", ""), body.get("contentType", ""),
                                      binding.template_version)
        return replace(candidate, message_ref=fresh) if candidate else None

    def _list_url(self, folder, lower_bound):
        if folder not in ("inbox", "junkemail") or lower_bound.tzinfo is None:
            raise MailboxError("MAPPING_INVALID")
        stamp = lower_bound.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        query = urlencode({"$select": METADATA, "$top": self.page_size,
                           "$filter": "receivedDateTime ge " + stamp,
                           "$orderby": "receivedDateTime desc"})
        return GRAPH_ROOT + "/me/mailFolders/" + folder + "/messages?" + query

    def _messages(self, result):
        values = result.get("value")
        if not isinstance(values, list) or len(values) > self.page_size or any(not isinstance(v, dict) for v in values):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        return values

    @staticmethod
    def _ref(metadata, recipient_match, template_match):
        try:
            stamp = datetime.fromisoformat(metadata["receivedDateTime"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or not isinstance(metadata["id"], str) or not metadata["id"]:
                raise ValueError
            return MessageRef(metadata["id"], metadata.get("internetMessageId"), stamp,
                              recipient_match, template_match)
        except (KeyError, ValueError, TypeError):
            raise MailboxError("GRAPH_PROTOCOL_ERROR") from None
