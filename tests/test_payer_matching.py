from identity.models import IdentityQuery, MatchOutcome
from payer.models import MemberRecord
from payer.system import PayerSystem


def _member(
    record_id="PM-1",
    member_id="MEM-01374522",
    first_name="Devin",
    last_name="Kelley",
    dob="1949-01-16",
):
    return MemberRecord(
        member_record_id=record_id,
        payer_id="KAISER",
        member_id=member_id,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=dob,
        administrative_sex="M",
    )


def test_exact_member_id_matches_and_confirms_demographics():
    system = PayerSystem("KAISER", members=[_member()])

    result = system.resolve_member(
        IdentityQuery(
            member_id="MEM-01374522",
            first_name="Devin",
            last_name="Kelley",
            date_of_birth="1949-01-16",
        )
    )

    assert result.outcome == MatchOutcome.MATCHED
    assert result.matched_candidate_id == "PM-1"
    assert set(result.matched_fields) == {
        "member_id",
        "first_name",
        "last_name",
        "date_of_birth",
    }
    assert result.conflicting_fields == ()
    assert result.score == 1.0


def test_member_id_can_match_while_demographic_difference_is_exposed():
    system = PayerSystem(
        "KAISER",
        members=[_member(last_name="Kelly")],
    )

    result = system.resolve_member(
        IdentityQuery(
            member_id="MEM-01374522",
            first_name="Devin",
            last_name="Kelley",
            date_of_birth="1949-01-16",
        )
    )

    assert result.outcome == MatchOutcome.MATCHED
    assert result.matched_candidate_id == "PM-1"
    assert "last_name" in result.conflicting_fields
    assert "member_id" in result.matched_fields
    assert result.score < 1.0


def test_unknown_member_id_is_not_found_without_demographic_fallback():
    system = PayerSystem("KAISER", members=[_member()])

    result = system.resolve_member(
        IdentityQuery(
            member_id="MEM-NOT-THERE",
            first_name="Devin",
            last_name="Kelley",
            date_of_birth="1949-01-16",
        )
    )

    assert result.outcome == MatchOutcome.NOT_FOUND
    assert result.candidate_ids == ()


def test_exact_name_and_dob_can_match_without_member_id():
    system = PayerSystem("KAISER", members=[_member()])

    result = system.resolve_member(
        IdentityQuery(
            first_name="  DEVIN ",
            last_name="kelley",
            date_of_birth="1949-01-16",
        )
    )

    assert result.outcome == MatchOutcome.MATCHED
    assert result.matched_candidate_id == "PM-1"


def test_duplicate_demographic_candidates_are_ambiguous():
    system = PayerSystem(
        "KAISER",
        members=[
            _member(record_id="PM-1", member_id="MEM-1"),
            _member(record_id="PM-2", member_id="MEM-2"),
        ],
    )

    result = system.resolve_member(
        IdentityQuery(
            first_name="Devin",
            last_name="Kelley",
            date_of_birth="1949-01-16",
        )
    )

    assert result.outcome == MatchOutcome.AMBIGUOUS
    assert set(result.candidate_ids) == {"PM-1", "PM-2"}


def test_duplicate_member_id_records_are_ambiguous():
    system = PayerSystem(
        "KAISER",
        members=[
            _member(record_id="PM-1"),
            _member(record_id="PM-2"),
        ],
    )

    result = system.resolve_member(
        IdentityQuery(member_id="MEM-01374522")
    )

    assert result.outcome == MatchOutcome.AMBIGUOUS
    assert set(result.candidate_ids) == {"PM-1", "PM-2"}
