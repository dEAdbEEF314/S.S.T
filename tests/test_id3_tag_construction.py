from pathlib import Path

from sst.tagger import AudioTagger


class FakeFrame:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeTags:
    def __init__(self):
        self.frames = []

    def add(self, frame):
        self.frames.append(frame)

    def clear(self):
        self.frames.clear()

    def get(self, frame_id):
        for frame in self.frames:
            if getattr(frame, "frame_id", None) == frame_id:
                return frame
        return None


class FakeAudio:
    def __init__(self):
        self.tags = FakeTags()
        self.saved_v2_version = None

    def add_tags(self):
        self.tags = FakeTags()

    def save(self, v2_version=4):
        self.saved_v2_version = v2_version


def _patch_id3_frames(monkeypatch):
    import mutagen.id3 as id3

    for frame_name in ["TIT2", "TPE1", "TALB", "TCON", "TRCK", "TPOS", "COMM", "TPE2", "TCOM", "APIC", "TIT1", "TYER", "TLAN"]:
        monkeypatch.setattr(id3, frame_name, lambda _frame_name=frame_name, **kwargs: FakeFrame(frame_id=_frame_name, **kwargs))


def test_write_tags_uses_id3v23_frames_without_tpub(monkeypatch, tmp_path):
    import mutagen.aiff as aiff

    fake_audio = FakeAudio()
    monkeypatch.setattr(aiff, "AIFF", lambda file_path: fake_audio)
    _patch_id3_frames(monkeypatch)

    tagger = AudioTagger(tmp_path)
    file_path = tmp_path / "track.aif"
    file_path.write_bytes(b"dummy")

    tagger.write_tags(
        file_path,
        {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Dev, Pub",
            "genre": "STEAM VGM, Action",
            "label": "Ignored Label",
            "grouping": "Game, Steam",
            "comment": "Comment",
            "composer": "Composer",
            "year": "2024-10-01",
            "track_number": "7",
            "disc_number": "2/3",
            "language": "jpn",
        },
    )

    frame_ids = [frame.frame_id for frame in fake_audio.tags.frames]
    assert "TYER" in frame_ids
    assert "TPUB" not in frame_ids
    assert fake_audio.saved_v2_version == 3


def test_write_tags_truncates_comment_by_dropping_trailing_tags(monkeypatch, tmp_path):
    import mutagen.aiff as aiff

    fake_audio = FakeAudio()
    monkeypatch.setattr(aiff, "AIFF", lambda file_path: fake_audio)
    _patch_id3_frames(monkeypatch)

    tagger = AudioTagger(tmp_path)
    file_path = tmp_path / "track.aif"
    file_path.write_bytes(b"dummy")

    long_tags = "/ ".join([f"tag{i}" for i in range(400)])
    tagger.write_tags(
        file_path,
        {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Dev, Pub",
            "genre": "STEAM VGM, Action",
            "grouping": "Game, Steam",
            "comment": f"Existing, Game, https://store.steampowered.com/app/1, [{long_tags}]",
            "composer": "Composer",
            "year": "2024",
            "track_number": "7",
            "disc_number": "1/1",
            "language": "jpn",
        },
    )

    comm_frame = next(frame for frame in fake_audio.tags.frames if frame.frame_id == "COMM")
    assert len(str(comm_frame.text).encode("utf-16")) <= 2000
    assert "tag399" not in str(comm_frame.text)


def test_write_tags_adds_front_cover_apic(monkeypatch, tmp_path):
    import mutagen.aiff as aiff

    fake_audio = FakeAudio()
    monkeypatch.setattr(aiff, "AIFF", lambda file_path: fake_audio)
    _patch_id3_frames(monkeypatch)

    tagger = AudioTagger(tmp_path)
    file_path = tmp_path / "track.aif"
    file_path.write_bytes(b"dummy")
    artwork_path = tmp_path / "cover.jpg"
    artwork_path.write_bytes(b"jpeg-data")

    tagger.write_tags(
        file_path,
        {
            "title": "Song",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Dev, Pub",
            "genre": "STEAM VGM, Action",
            "grouping": "Game, Steam",
            "comment": "Comment",
            "composer": "Composer",
            "year": "2024",
            "track_number": "7",
            "disc_number": "1/1",
            "language": "jpn",
        },
        artwork_path=artwork_path,
    )

    apic_frame = next(frame for frame in fake_audio.tags.frames if frame.frame_id == "APIC")
    assert apic_frame.type == 3
    assert apic_frame.mime == "image/jpeg"
    assert apic_frame.data == b"jpeg-data"


def test_write_tags_marks_unconfirmed_fields_without_numeric_placeholders(monkeypatch, tmp_path):
    import mutagen.aiff as aiff

    fake_audio = FakeAudio()
    monkeypatch.setattr(aiff, "AIFF", lambda file_path: fake_audio)
    _patch_id3_frames(monkeypatch)

    tagger = AudioTagger(tmp_path)
    file_path = tmp_path / "unconfirmed.aif"
    file_path.write_bytes(b"dummy")

    tagger.write_tags(
        file_path,
        {
            "title": "Original title",
            "artist": "Artist",
            "album": "Album",
            "album_artist": "Dev, Pub",
            "genre": "STEAM VGM",
            "grouping": "Game, Steam",
            "comment": "Review output",
            "composer": "Composer",
            "year": "2024",
            "track_number": "7",
            "disc_number": "1/1",
            "language": "jpn",
            "unconfirmed_fields": ["title", "track_number", "year"],
        },
    )

    frames = {frame.frame_id: frame for frame in fake_audio.tags.frames}
    assert frames["TIT2"].text == "S.S.T Unconfirmed"
    assert "TRCK" not in frames
    assert "TYER" not in frames
    assert frames["TPOS"].text == "1/1"
    assert "S.S.T Unconfirmed" in str(frames["COMM"].text)
    assert "title" in str(frames["COMM"].text)
    assert "track_number" in str(frames["COMM"].text)