from adoif.services.notes import NoteService
from adoif.settings import Settings


def test_note_service_adds_and_lists(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    service = NoteService(settings)

    note = service.add_note(doi="10.1/test", body="Reflection", tags=["psy305"])
    assert note.doi == "10.1/test"
    assert "psy305" in note.tags

    notes = service.list_notes()
    assert len(notes) == 1
    assert notes[0].body == "Reflection"
