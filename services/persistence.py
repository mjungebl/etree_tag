from __future__ import annotations

from typing import Iterable

from sqliteetreedb import SQLiteEtreeDB


class TrackMetadataRepository:
    """Facade around the SQLite layer for track metadata operations."""

    def __init__(self, db: SQLiteEtreeDB) -> None:
        self._db = db

    @property
    def db_path(self) -> str:
        return self._db.db_path

    def fetch_tracks(self, shnid: int, md5key: int | None = None):
        return self._db.get_track_metadata(shnid, md5key)

    def overwrite_tracks(
        self,
        shnid: int,
        records: Iterable[tuple],
        *,
        md5key: int | None = None,
    ) -> None:
        self._db.insert_track_metadata(
            shnid,
            list(records),
            overwrite=True,
            md5key=md5key,
        )

    def close(self) -> None:
        self._db.close()
