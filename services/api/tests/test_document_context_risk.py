from app.services.risk_guardrail import evaluate_risk, strip_document_context


def test_ehr_document_does_not_trigger_current_symptom_risk():
    text = (
        "[已查看附件: ehr.pdf]\n"
        "[文档上下文: ehr.pdf]\n既往记录：胸痛、呼吸困难。\n[/文档上下文]"
    )

    assert strip_document_context(text) == ""
    assert evaluate_risk(text) == ("normal", [])


def test_current_user_symptom_still_triggers_with_ehr_attached():
    text = (
        "我现在胸痛\n[已查看附件: ehr.pdf]\n"
        "[文档上下文: ehr.pdf]\n历史病历内容\n[/文档上下文]"
    )

    assert evaluate_risk(text)[0] == "high"
