"""内置医学知识数据 + 加载逻辑，支持文本切分和真实文档摄入。"""
from __future__ import annotations

import logging
from pathlib import Path

from app.services.rag_retriever import add_documents, clear_collection
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── 内置医学知识库 ─────────────────────────────────────────────────────────
# 每条知识：(文档文本, metadata)
# metadata 包含 category(类别)、source(来源)、keywords(关键词)

MEDICAL_KNOWLEDGE: list[tuple[str, dict]] = [
    # ── 常见疾病症状与分诊指南 ──────────────────────────────────────────────
    (
        "高血压：收缩压≥140mmHg和/或舒张压≥90mmHg可诊断。常见症状包括头晕、头痛、耳鸣、心悸。"
        "长期未控制可导致心脑肾损害。分诊建议：收缩压≥180或舒张压≥120为高血压危象，需急诊处理；"
        "160-180/100-120建议当日就诊；140-160/90-100建议门诊随访。"
        "生活干预：低盐饮食（每日<6g）、规律运动、戒烟限酒、控制体重。",
        {"category": "疾病分诊", "source": "中国高血压防治指南", "keywords": "高血压 头晕 头痛 心悸 血压高"},
    ),
    (
        "2型糖尿病：空腹血糖≥7.0mmol/L或餐后2小时血糖≥11.1mmol/L可诊断。"
        "典型症状：三多一少（多饮、多尿、多食、体重下降）。"
        "急性并发症：糖尿病酮症酸中毒（恶心呕吐、腹痛、呼吸深快）、高渗性昏迷。"
        "分诊建议：血糖>33.3mmol/L或出现酮症酸中毒症状需急诊；血糖16.7-33.3建议当日就诊；"
        "新发现空腹血糖7-13.9建议门诊内分泌科。",
        {"category": "疾病分诊", "source": "中国2型糖尿病防治指南", "keywords": "糖尿病 血糖高 多饮 多尿 口渴"},
    ),
    (
        "冠心病：冠状动脉粥样硬化导致心肌缺血缺氧。症状：胸骨后压榨性疼痛，可放射至左肩、左臂、下颌。"
        "持续3-5分钟，休息或含服硝酸甘油可缓解。急性心肌梗死：胸痛持续>30分钟，伴大汗、濒死感。"
        "分诊建议：疑似急性心梗立即拨打120急诊；稳定性心绞痛发作频繁建议心内科门诊。",
        {"category": "疾病分诊", "source": "冠心病诊疗指南", "keywords": "胸痛 胸闷 心绞痛 心梗 冠心病"},
    ),
    (
        "上呼吸道感染（感冒）：鼻塞、流涕、咽痛、咳嗽，可伴低热（<38.5°C）。"
        "病程一般5-7天自限。分诊建议：体温<38.5°C且无基础疾病可居家对症处理；"
        "体温≥39°C持续3天不退、伴呼吸困难、脓性痰建议就诊。"
        "用药：对乙酰氨基酚或布洛芬退热，不建议抗生素（病毒性）。",
        {"category": "疾病分诊", "source": "普通感冒诊疗指南", "keywords": "感冒 发烧 咳嗽 鼻塞 咽痛 流涕"},
    ),
    (
        "支气管哮喘：反复发作的喘息、气急、胸闷或咳嗽，常在夜间及凌晨加重。"
        "发作时双肺可闻及散在或弥漫性哮鸣音。急性发作分诊：不能说话、大汗淋漓、意识模糊为危重，"
        "立即急诊；说话困难、呼吸急促为重度，当日急诊；活动后气促为轻中度，门诊调整用药。"
        "日常管理：避免过敏原，规律使用吸入性糖皮质激素。",
        {"category": "疾病分诊", "source": "支气管哮喘防治指南", "keywords": "哮喘 喘息 气急 呼吸困难 胸闷"},
    ),
    (
        "急性胃肠炎：恶心、呕吐、腹痛、腹泻，多由病毒或细菌感染引起。"
        "分诊建议：出现脱水征象（口干、尿少、眼窝凹陷）需就医补液；"
        "血便、高热不退、剧烈腹痛需排除外科急腹症；轻症可口服补液盐，清淡饮食。",
        {"category": "疾病分诊", "source": "消化内科诊疗常规", "keywords": "腹泻 呕吐 腹痛 胃肠炎 拉肚子"},
    ),
    (
        "偏头痛：反复发作的单侧搏动性头痛，常伴恶心、畏光、畏声。"
        "先兆型可出现视觉闪光暗点。分诊建议：突发剧烈头痛（雷击样）需急诊排除蛛网膜下腔出血；"
        "反复发作影响生活建议神经内科门诊；急性发作可用曲坦类或NSAIDs。",
        {"category": "疾病分诊", "source": "中国偏头痛诊疗指南", "keywords": "偏头痛 头痛 恶心 呕吐"},
    ),
    (
        "甲状腺功能亢进：心悸、手抖、怕热多汗、体重下降、烦躁易怒、甲状腺肿大。"
        "分诊建议：甲亢危象（高热>39°C、心率>140次/分、谵妄）需急诊；"
        "新发甲亢症状建议内分泌科门诊查甲功。"
        "甲状腺功能减退：畏寒、乏力、浮肿、便秘、记忆力减退。TSH升高、FT4降低。",
        {"category": "疾病分诊", "source": "甲状腺疾病诊疗指南", "keywords": "甲亢 甲减 甲状腺 心悸 手抖 怕热"},
    ),
    (
        "泌尿系统感染（尿路感染）：尿频、尿急、尿痛，可伴腰痛、发热。"
        "女性多见。分诊建议：伴高热、腰痛提示上尿路感染（肾盂肾炎），需就诊；"
        "单纯下尿路感染可多饮水、口服抗生素（如左氧氟沙星）。"
        "反复发作需排除泌尿系结构异常。",
        {"category": "疾病分诊", "source": "泌尿外科诊疗常规", "keywords": "尿频 尿急 尿痛 尿路感染"},
    ),
    (
        "焦虑障碍：持续6个月以上的过度担忧、紧张不安，伴睡眠障碍、注意力不集中、肌肉紧张。"
        "可出现心悸、出汗、颤抖等躯体症状。分诊建议：伴自杀意念需精神科急诊；"
        "影响日常功能建议精神心理科门诊。治疗：认知行为治疗+药物（SSRIs）。",
        {"category": "疾病分诊", "source": "焦虑障碍诊疗指南", "keywords": "焦虑 紧张 失眠 担忧 恐慌"},
    ),
    (
        "贫血：血红蛋白男性<120g/L、女性<110g/L。症状：面色苍白、头晕、乏力、心悸、活动后气促。"
        "常见原因：缺铁性贫血（月经量多、消化道出血）、巨幼细胞性贫血、再障。"
        "分诊建议：Hb<60g/L为重度贫血需紧急处理；60-90g/L建议尽快就诊查因；"
        ">90g/L门诊查血常规+铁代谢。",
        {"category": "化验解读", "source": "血液病诊疗指南", "keywords": "贫血 血红蛋白低 头晕 乏力 苍白"},
    ),
    (
        "痛风：血尿酸升高导致关节急性炎症，典型为第一跖趾关节红肿热痛。"
        "诱因：高嘌呤饮食、饮酒、脱水。分诊建议：急性发作期可用秋水仙碱或NSAIDs；"
        "反复发作需降尿酸治疗（别嘌醇/非布司他）。饮食控制：避免内脏、海鲜、啤酒。",
        {"category": "疾病分诊", "source": "痛风诊疗指南", "keywords": "痛风 尿酸高 关节痛 脚痛"},
    ),
    # ── 常见化验指标解读 ──────────────────────────────────────────────────
    (
        "血常规-白细胞(WBC)：正常值(4-10)×10^9/L。升高见于细菌感染、炎症、白血病；"
        "降低见于病毒感染、药物影响、骨髓抑制。中性粒细胞升高提示细菌感染，"
        "淋巴细胞升高提示病毒感染。分类计数比总数更有诊断价值。",
        {"category": "化验解读", "source": "临床检验手册", "keywords": "白细胞 WBC 感染 血常规"},
    ),
    (
        "血常规-血红蛋白(Hb)：正常男性120-160g/L，女性110-150g/L。"
        "降低提示贫血：轻度90-120、中度60-90、重度<60。"
        "MCV<80fL为小细胞贫血（缺铁最常见），MCV>100fL为大细胞贫血（叶酸/B12缺乏），"
        "MCV正常为正细胞贫血（慢性病、出血）。",
        {"category": "化验解读", "source": "临床检验手册", "keywords": "血红蛋白 贫血 Hb MCV"},
    ),
    (
        "血常规-血小板(PLT)：正常值(100-300)×10^9/L。"
        "降低见于免疫性血小板减少症(ITP)、再障、脾功能亢进、DIC。"
        "<50×10^9/L有自发出血风险，<20×10^9/L需紧急处理。"
        "升高见于感染后反应性增多、骨髓增殖性疾病。",
        {"category": "化验解读", "source": "临床检验手册", "keywords": "血小板 PLT 出血"},
    ),
    (
        "肝功能-谷丙转氨酶(ALT)：正常值0-40U/L。升高提示肝细胞损伤："
        "病毒性肝炎、药物性肝损、脂肪肝、酒精性肝病。"
        "ALT>正常上限10倍提示急性肝损伤。AST/ALT比值>2提示酒精性肝病。"
        "结合胆红素、白蛋白、凝血功能综合判断肝功能。",
        {"category": "化验解读", "source": "肝脏疾病诊疗指南", "keywords": "转氨酶 ALT 肝功能 肝损伤"},
    ),
    (
        "肾功能-肌酐(Cr)：正常男性54-106μmol/L，女性44-97μmol/L。"
        "升高提示肾功能下降。eGFR计算公式评估肾小球滤过率："
        ">90为正常，60-89为轻度下降，30-59为中度下降，15-29为重度下降，<15为肾衰竭。"
        "尿素氮(BUN)升高也见于脱水、高蛋白饮食，特异性不如肌酐。",
        {"category": "化验解读", "source": "肾脏病诊疗指南", "keywords": "肌酐 肾功能 eGFR 肾衰"},
    ),
    (
        "血糖-空腹血糖(FPG)：正常3.9-6.1mmol/L。6.1-7.0为空腹血糖受损(IFG)，"
        "≥7.0考虑糖尿病。糖化血红蛋白(HbA1c)：正常<6.5%，"
        "反映近2-3个月平均血糖水平。餐后2小时血糖：正常<7.8mmol/L，"
        "7.8-11.1为糖耐量异常(IGT)，≥11.1考虑糖尿病。",
        {"category": "化验解读", "source": "糖尿病防治指南", "keywords": "血糖 空腹血糖 糖化血红蛋白 HbA1c"},
    ),
    (
        "血脂四项：总胆固醇(TC)<5.2mmol/L，甘油三酯(TG)<1.7mmol/L，"
        "低密度脂蛋白(LDL-C)<3.4mmol/L，高密度脂蛋白(HDL-C)>1.0mmol/L。"
        "LDL-C是动脉粥样硬化的主要危险因素，冠心病患者需<1.8mmol/L。"
        "TG>5.6mmol/L有急性胰腺炎风险。",
        {"category": "化验解读", "source": "血脂异常诊疗指南", "keywords": "血脂 胆固醇 甘油三酯 LDL HDL"},
    ),
    (
        "甲状腺功能：TSH正常0.27-4.2mIU/L。TSH降低+FT3/FT4升高=甲亢；"
        "TSH升高+FT4降低=甲减。亚临床甲亢：TSH低但FT3/FT4正常；"
        "亚临床甲减：TSH高但FT4正常。甲状腺抗体(TPOAb、TgAb)升高提示自身免疫性甲状腺病。",
        {"category": "化验解读", "source": "甲状腺疾病诊疗指南", "keywords": "TSH 甲功 甲状腺 FT3 FT4"},
    ),
    (
        "尿常规：尿蛋白阳性提示肾脏疾病（肾炎、肾病综合征）；"
        "尿潜血阳性需排除泌尿系结石、肿瘤、感染；"
        "尿白细胞阳性提示尿路感染；尿糖阳性需查血糖排除糖尿病；"
        "尿酮体阳性见于饥饿、糖尿病酮症。需结合镜检综合判断。",
        {"category": "化验解读", "source": "临床检验手册", "keywords": "尿常规 尿蛋白 尿糖 尿潜血"},
    ),
    # ── 常见药物使用注意事项 ──────────────────────────────────────────────
    (
        "阿司匹林：抗血小板聚集，用于心脑血管疾病二级预防。常见不良反应：胃肠道出血、过敏。"
        "禁忌：活动性消化道溃疡、出血性疾病、阿司匹林哮喘。"
        "与其他抗凝药（华法林）合用增加出血风险。肠溶片应餐前服用。",
        {"category": "药物知识", "source": "药理学教材", "keywords": "阿司匹林 抗血小板 出血"},
    ),
    (
        "二甲双胍：2型糖尿病一线用药。常见不良反应：胃肠道反应（恶心、腹泻）、乳酸酸中毒（罕见）。"
        "禁忌：肾功能不全（eGFR<30）、严重肝功能不全、酗酒。"
        "与碘造影剂合用时需暂停48小时。建议餐中或餐后服用减少胃肠反应。",
        {"category": "药物知识", "source": "糖尿病用药指南", "keywords": "二甲双胍 降糖药 糖尿病"},
    ),
    (
        "他汀类药物（阿托伐他汀、瑞舒伐他汀）：降胆固醇，用于高脂血症和心血管疾病预防。"
        "常见不良反应：肌肉酸痛（横纹肌溶解罕见但严重）、肝酶升高。"
        "禁忌：活动性肝病、妊娠。与红霉素、克拉霉素合用增加肌病风险。建议晚间服用。",
        {"category": "药物知识", "source": "血脂异常用药指南", "keywords": "他汀 降脂药 胆固醇 肌肉痛"},
    ),
    (
        "布洛芬：非甾体抗炎药(NSAID)，用于退热、止痛、消炎。"
        "常见不良反应：胃肠道刺激、肾功能损害、心血管风险增加。"
        "禁忌：活动性消化道溃疡、严重心衰、晚期肾病。与阿司匹林合用降低其抗血小板作用。"
        "与华法林合用增加出血风险。建议餐后服用。",
        {"category": "药物知识", "source": "药理学教材", "keywords": "布洛芬 退烧 止痛 消炎"},
    ),
    (
        "华法林：口服抗凝药，用于房颤、深静脉血栓等。治疗窗窄，需定期监测INR（目标2-3）。"
        "食物相互作用：富含维生素K的食物（菠菜、西兰花）会降低药效。"
        "药物相互作用极多：阿司匹林、NSAIDs增加出血；利福平、卡马西平降低药效。"
        "漏服不能补双倍剂量。",
        {"category": "药物知识", "source": "抗凝治疗指南", "keywords": "华法林 抗凝 INR 出血"},
    ),
    # ── 急救知识 ─────────────────────────────────────────────────────────
    (
        "急性胸痛急救：立即停止活动，半卧位休息。若怀疑心梗（持续胸痛>15分钟、大汗、濒死感），"
        "立即拨打120。嚼服阿司匹林300mg（无禁忌时）。含服硝酸甘油（血压不低时），"
        "5分钟可重复，最多3次。若心脏骤停，立即CPR+AED。"
        "切勿自行驾车就医。",
        {"category": "急救知识", "source": "急性冠脉综合征救治流程", "keywords": "胸痛 心梗 急救 CPR"},
    ),
    (
        "脑卒中（中风）急救：FAST识别法——Face(面部不对称)、Arm(手臂无力)、Speech(言语不清)、"
        "Time(立即拨打120)。发病4.5小时内是溶栓黄金时间窗。"
        "让患者平卧，头偏向一侧防误吸。不要喂食喂水。记录发病时间。"
        "切勿自行用药（阿司匹林在出血性卒中有害）。",
        {"category": "急救知识", "source": "脑卒中急救指南", "keywords": "中风 脑卒中 偏瘫 说话不清"},
    ),
    (
        "过敏性休克急救：接触过敏原后出现呼吸困难、面色苍白、血压下降、荨麻疹。"
        "立即拨打120。让患者平卧，抬高下肢。肾上腺素0.3-0.5mg肌肉注射（大腿外侧）为首选。"
        "开放气道，必要时CPR。有已知严重过敏史者应随身携带肾上腺素自动注射器。",
        {"category": "急救知识", "source": "过敏性休克救治指南", "keywords": "过敏 休克 呼吸困难 荨麻疹"},
    ),
    (
        "低血糖急救：血糖<3.9mmol/L。症状：心慌、手抖、出冷汗、饥饿感、意识模糊。"
        "清醒患者立即口服15-20g速效糖（葡萄糖片、含糖饮料、糖果）。"
        "15分钟后复测血糖，未纠正重复给糖。意识不清者禁止喂食，侧卧位，拨打120。"
        "糖尿病患者应随身携带糖果和血糖仪。",
        {"category": "急救知识", "source": "低血糖处理指南", "keywords": "低血糖 心慌 手抖 出冷汗"},
    ),
    (
        "中暑急救：高温环境下出现头晕、恶心、体温升高、意识改变。"
        "先兆中暑：转移到阴凉处，补充含盐饮料，物理降温。"
        "热射病（体温>40°C、意识障碍）：立即拨打120，冰敷大血管处（颈部、腋下、腹股沟），"
        "冷水浸泡或喷雾+风扇。不要给意识不清者喂水。",
        {"category": "急救知识", "source": "中暑救治指南", "keywords": "中暑 高热 热射病"},
    ),
]


def _split_text(text: str, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[str]:
    """使用 langchain_text_splitters 切分长文本。"""
    if chunk_size is None:
        chunk_size = settings.RAG_CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = settings.RAG_CHUNK_OVERLAP

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", "，", " "],
        length_function=len,
    )
    return splitter.split_text(text)


def load_knowledge() -> dict:
    """加载内置医学知识到 ChromaDB。返回统计信息。"""
    clear_collection()

    documents = [doc for doc, _ in MEDICAL_KNOWLEDGE]
    metadatas = [meta for _, meta in MEDICAL_KNOWLEDGE]
    count = add_documents(documents, metadatas)

    return {
        "loaded": count,
        "categories": list({meta.get("category", "") for _, meta in MEDICAL_KNOWLEDGE}),
    }


def load_documents_from_files(file_paths: list[str], category: str = "医学文献") -> dict:
    """从文件列表加载文档，支持文本切分。

    支持 .txt, .md, .pdf, .docx 格式。
    长文档会按 RAG_CHUNK_SIZE 切分后分别入库。
    """
    from pathlib import Path as P

    all_docs: list[str] = []
    all_metas: list[dict] = []

    for fp in file_paths:
        p = P(fp)
        if not p.exists():
            logger.warning(f"文件不存在: {fp}")
            continue

        ext = p.suffix.lower()
        text = ""

        if ext in (".txt", ".md"):
            text = p.read_text(encoding="utf-8", errors="ignore")
        elif ext == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(p))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                logger.warning(f"PDF 解析失败 {fp}: {e}")
                continue
        elif ext == ".docx":
            try:
                from docx import Document
                doc = Document(str(p))
                text = "\n".join(para.text for para in doc.paragraphs if para.text)
            except Exception as e:
                logger.warning(f"DOCX 解析失败 {fp}: {e}")
                continue
        else:
            logger.warning(f"不支持的文件格式: {ext}")
            continue

        text = text.strip()
        if not text:
            continue

        # 切分长文本
        chunks = _split_text(text)
        for i, chunk in enumerate(chunks):
            all_docs.append(chunk)
            all_metas.append({
                "category": category,
                "source": p.name,
                "keywords": "",
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

    if all_docs:
        count = add_documents(all_docs, all_metas)
        logger.info(f"从 {len(file_paths)} 个文件加载了 {count} 个文档片段")
        return {"loaded": count, "files": file_paths}

    return {"loaded": 0, "files": file_paths}
