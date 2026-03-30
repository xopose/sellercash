from app.services.knowledge import _chunk_text, _extract_events_from_chunk


def test_chunk_text_small_document_produces_single_chunk() -> None:
    text = "С 15 мая 2026 комиссия увеличена на +1.5%."
    chunks = _chunk_text(text)
    assert len(chunks) == 1


def test_event_extractor_detects_core_events() -> None:
    text = (
        "С 15 мая 2026 комиссия увеличивается на +1.5%. "
        "Срок выплат увеличен на +3 дня. "
        "Логистика дорожает на +8%."
    )
    events = _extract_events_from_chunk(text)
    event_types = {e["event_type"] for e in events}

    assert "commission_change_pct" in event_types
    assert "payout_delay_days" in event_types
    assert "logistics_change_pct" in event_types
