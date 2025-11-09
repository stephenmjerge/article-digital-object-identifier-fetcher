from adoif.services.extraction import ExtractionService
from adoif.settings import Settings


def test_extraction_service_records_pico(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    service = ExtractionService(settings)
    record = service.upsert_record(
        doi="10.1/abc",
        population="Adults",
        intervention="Therapy",
        comparator="Placebo",
        outcomes_summary="Improved",
        notes="N/A",
        status="draft",
    )
    assert record.population == "Adults"
    outcome = service.add_outcome(
        extraction_id=record.id,
        description="Response rate",
        effect_size=1.5,
        effect_unit="RR",
        ci_low=1.2,
        ci_high=1.8,
        p_value=0.01,
    )
    assert outcome.description == "Response rate"
    records = service.list_records()
    assert len(records) == 1
