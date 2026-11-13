from __future__ import annotations

from .models import Tag


class TagRegistry:
    """In-memory one-tag-per-tyre registry for the first milestone."""

    def __init__(self) -> None:
        self._by_epc: dict[str, Tag] = {}
        self._epc_by_tyre: dict[str, str] = {}

    def register(self, tag: Tag) -> None:
        if tag.epc in self._by_epc:
            raise ValueError(f"EPC already registered: {tag.epc}")
        if tag.tyre_id in self._epc_by_tyre:
            raise ValueError(f"Tyre already has a tag: {tag.tyre_id}")
        self._by_epc[tag.epc] = tag
        self._epc_by_tyre[tag.tyre_id] = tag.epc

    def get_by_epc(self, epc: str) -> Tag | None:
        return self._by_epc.get(epc.replace(" ", "").upper())

    def get_by_tyre(self, tyre_id: str) -> Tag | None:
        epc = self._epc_by_tyre.get(tyre_id)
        return self._by_epc.get(epc) if epc else None

    def __len__(self) -> int:
        return len(self._by_epc)
