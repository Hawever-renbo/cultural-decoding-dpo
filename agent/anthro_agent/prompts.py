"""Prompt templates for levels 2-3 and the decode step, in two languages.

`zh` is the wording the pipeline was developed with; `en` is its translation, used when the analysis should read
in English. Both ask for the same structures. Model output is normalised to the canonical (English) keys below.

Design rule behind every prompt: say what the model must not do (bare-noun names, names with no concrete action,
names detached from the phenomenon, merged unrelated themes) and leave how to phrase and cluster to the model.
"""
import json

NL = "\n"
C6_SLOTS = ["P", "CC", "Ctx", "IC", "S", "Csq"]
C6_NAMES = {"en": "P phenomenon, CC causal conditions, Ctx context, IC intervening conditions, S action strategies, Csq consequences",
            "zh": "P 核心现象、CC 因果条件、Ctx 背景、IC 中介条件、S 行动策略、Csq 结果"}
C6_ALIAS = {
    "p": "P", "核心现象": "P", "核心现象p": "P", "现象": "P", "phenomenon": "P",
    "cc": "CC", "因果条件": "CC", "因果条件cc": "CC", "原因": "CC", "causal conditions": "CC", "causal condition": "CC",
    "ctx": "Ctx", "背景": "Ctx", "背景ctx": "Ctx", "背景条件": "Ctx", "context": "Ctx",
    "ic": "IC", "中介条件": "IC", "中介条件ic": "IC", "中介": "IC", "intervening conditions": "IC", "intervening condition": "IC",
    "s": "S", "行动策略": "S", "行动策略s": "S", "策略": "S", "action strategies": "S", "strategies": "S", "strategy": "S",
    "csq": "Csq", "结果": "Csq", "结果csq": "Csq", "后果": "Csq", "consequences": "Csq", "consequence": "Csq",
}
REL_TYPES = ["causal", "conditional", "contextual", "intervening", "action", "consequence", "temporal", "includes",
             "opposes", "abstracts_to"]
REL_ZH = ["因果", "条件", "背景", "中介", "行动", "结果", "时序", "包含", "对立", "abstracts_to"]
REL_ALIAS = dict(zip(REL_ZH, REL_TYPES))
# Names may not END on these bare nouns (gate G8). Only a floor: no whitelist of allowed head words.
BLACKLIST = {"zh": ["背景", "策略", "偏好", "结果", "文化", "环境"],
             "en": ["background", "strategy", "strategies", "preference", "preferences", "outcome", "outcomes",
                    "result", "results", "culture", "environment"]}
DECODE_KEYS = ["surface", "functional", "emotional", "social", "cultural", "cultural_logic", "symbolic_meaning",
               "counter_example"]
DECODE_ZH = ["表层", "功能层", "情感层", "社会层", "文化层", "文化逻辑", "象征意义", "反例"]
DECODE_ALIAS = dict(zip(DECODE_ZH, DECODE_KEYS))
LENS_KEYS = ["thick_description", "contextualisation", "emic_etic", "chain_of_meaning", "reflexivity"]
LENS_ZH = ["厚描述", "情境化", "主位客位", "意义链", "反思性"]


def c6_normalize(slot):
    return C6_ALIAS.get(slot.strip().lower(), "") if isinstance(slot, str) else ""


def rel_normalize(rel_type):
    t = (rel_type or "").strip()
    return REL_ALIAS.get(t, t.lower())


def _j(obj):
    return json.dumps(obj, ensure_ascii=False)


def _fb(lang, feedback):
    if not feedback:
        return ""
    if lang == "zh":
        return NL + "上一轮未通过的检查（本轮须修正）：" + "；".join(feedback)
    return NL + "Checks that failed in the previous round (fix them in this one): " + "; ".join(feedback)


PREAMBLE = {
    "zh": """你是扎根理论三级编码器，做「编码压缩」：以研究焦点 Y 为锚点，把原始资料逐级压缩为概念→范畴→核心范畴，只保留与 Y 相关的信息、舍弃无关冗余。

三层分工：开放编码=局部模式（概念）、主轴编码=关系模式（范畴+关系）、选择性编码=总纲（核心范畴+故事线）。

注意：Y 由研究问题声明，不能由编码产出反向定义后自证保真；若 Y 版本未固定，只报结构/保真等代理指标，不做互信息定论。""",
    "en": """You are a grounded-theory three-level coder doing "coding as compression": with the research focus Y as the anchor, compress the raw material step by step into concepts -> categories -> a core category, keeping only what bears on Y and discarding the rest.

Division of labour: open coding = local patterns (concepts); axial coding = relational patterns (categories and relations); selective coding = the overall line (core category and storyline).

Note: Y is declared by the research question. It must not be redefined from the coding output and then used to certify its own fidelity. If Y is not fixed, report only structural and fidelity proxies and make no mutual-information claim.""",
}


def open_dialog(lang, focus, dialog, y_current="", feedback=None):
    """Level 1 on a general model, used only when no post-trained open-coding model is configured."""
    if lang == "zh":
        fb = ("上一轮核心范畴 Y=" + y_current + "。围绕它反向筛选：只保留相关资料，删噪声。") if y_current else ""
        fb2 = ("；上一轮未过闸机：" + "；".join(feedback)) if feedback else ""
        return (PREAMBLE["zh"] + NL + "你是扎根理论开放编码器。研究焦点：" + focus + "。" + fb + fb2
                + NL + "逐行检视访谈提取语义标签：贴近原话短句、低抽象、按输入规模穷尽提取（大输入多、小输入少，不硬凑），各附原文 evidence（逐字摘自原文）。只保留与焦点相关的标签，丢弃与焦点无关的内容。"
                '只输出 JSON 数组：[{"label":"","evidence":""}]'
                + NL + "全文：" + NL + dialog)
    fb = ("Core category of the previous round: Y = " + y_current + ". Filter around it: keep only relevant material, drop noise. ") if y_current else ""
    fb2 = ("Gates not passed in the previous round: " + "; ".join(feedback) + ". ") if feedback else ""
    return (PREAMBLE["en"] + NL + "You are a grounded-theory open coder. Research focus: " + focus + ". " + fb + fb2
            + NL + "Go through the interview line by line and extract semantic labels: short phrases close to the speaker's own words, low abstraction, exhaustive in proportion to the input (more for a large input, fewer for a small one; do not pad). Give each label its evidence, copied verbatim from the text. Keep only labels that bear on the focus; drop the rest. "
            'Output only a JSON array: [{"label":"","evidence":""}]'
            + NL + "Full text:" + NL + dialog)


def concepts(lang, focus, labeled, feedback=None):
    if lang == "zh":
        return (PREAMBLE["zh"] + NL + "你是扎根理论概念层编码器。研究焦点：" + focus + "。"
                + NL + "把语义标签概括为概念：研究者构造的抽象概念（客位码），中文命名，信息密度高——可含多层修饰词（人群/条件 + 机制 + 核心名词，如「担责焦虑驱动的机器答案复核」），不要用受访者口语原话当概念名。适度抽象，数量按需（不硬凑）。"
                + NL + "每个概念必须是一个连贯的抽象（一个主题），禁止把两个不相关主题用「与/和」硬并成一个概念名；不相关的标签拆成多个概念。"
                + NL + "每个概念给键值属性（从人群、场景、触发、动机、机制、条件、结果 中按需选，不强制数量）。"
                + NL + "label_ids 填该概念吸收的语义标签索引（从下面标签的 i 字段选，可多个，如 [3,17,42]）。尽量让每个与焦点相关的标签都被某个概念吸收。"
                + _fb(lang, feedback) + NL
                + '只输出 JSON 数组：[{"concept":"","freq":0,"label_ids":[0],"attributes":{"人群":"","动机":""}}]'
                + NL + "语义标签（带索引 i）：" + NL + _j(labeled))
    return (PREAMBLE["en"] + NL + "You are a grounded-theory concept-level coder. Research focus: " + focus + "."
            + NL + 'Generalise the semantic labels into concepts: abstract codes constructed by the researcher (etic codes), named in English and information-dense. A name may stack modifiers (who or under what condition + mechanism + head noun, e.g. "liability-anxiety-driven double-checking of machine answers"). Do not use a participant\'s verbatim phrase as a concept name. Abstract moderately; give as many concepts as the material needs (do not pad).'
            + NL + 'Each concept must be one coherent abstraction (one theme). Never join two unrelated themes with "and" in one name; split unrelated labels into separate concepts.'
            + NL + "Give each concept key-value attributes (choose as needed from: actor, setting, trigger, motive, mechanism, condition, consequence; no fixed number)."
            + NL + "label_ids lists the indices of the labels this concept absorbs (the i field below; several allowed, e.g. [3,17,42]). Try to have every label that bears on the focus absorbed by some concept."
            + _fb(lang, feedback) + NL
            + 'Output only a JSON array: [{"concept":"","freq":0,"label_ids":[0],"attributes":{"actor":"","motive":""}}]'
            + NL + "Semantic labels (with index i):" + NL + _j(labeled))


def axial(lang, focus, concept_list, naming_examples=None, feedback=None):
    shape = '{"categories":[{"name":"","c6_slot":"","concepts":[]}],"relations":[{"from":"","to":"","type":"","evidence":"","confidence":0.8}]}'
    if lang == "zh":
        ref = (NL + "范畴命名参照（仅参考，勿照抄其格式）：" + NL + NL.join(naming_examples)) if naming_examples else ""
        return (PREAMBLE["zh"] + NL + "你是扎根理论主轴编码器。研究焦点：" + focus + "。"
                + NL + "把概念抽象为范畴（≥5 个，自然聚类，不硬凑数量）。范畴 = 关系/过程的抽象，不是话题分组。禁止：纯名词（黑名单：" + "/".join(BLACKLIST["zh"]) + "）、名字不落到具体行为（必须含一个具体动作动词，不能停在「实践/协商/需求/想象」这类无动作的泛化收尾）、把不相关概念硬并成一个范畴。范畴名用中文，且必须是本现象（研究焦点）的构成维度（现象绑定）。"
                + ref
                + NL + "每个范畴标 c6_slot 短标签(" + "/".join(C6_SLOTS) + "：" + C6_NAMES["zh"] + ")，六要素全覆盖；范畴间给类型化边(" + "/".join(REL_ZH) + ")带 evidence 和 confidence（0-1 关系确信度）。categories 里的 concepts 须照抄下面给出的概念名。"
                + _fb(lang, feedback) + NL
                + "只输出 JSON：" + shape
                + NL + "概念：" + NL + _j(concept_list))
    ref = (NL + "Naming references (for orientation only; do not copy their format):" + NL + NL.join(naming_examples)) if naming_examples else ""
    return (PREAMBLE["en"] + NL + "You are a grounded-theory axial coder. Research focus: " + focus + "."
            + NL + "Abstract the concepts into categories (at least 5, clustered naturally; do not pad). A category is an abstraction of a relation or a process, not a topic group. Not allowed: a bare noun as the name (blacklist: " + " / ".join(BLACKLIST["en"][:1] + ["strategy", "preference", "outcome", "culture", "environment"]) + '); a name that does not land on a concrete action (it must contain a concrete action verb, e.g. as a gerund, and must not stop at an action-less generality such as "practice", "negotiation", "needs", "imagination"); merging unrelated concepts into one category. Name categories in English. Each must be a constitutive dimension of the phenomenon under study (bound to the phenomenon).'
            + ref
            + NL + "Tag each category with a c6_slot (" + "/".join(C6_SLOTS) + ": " + C6_NAMES["en"] + "); all six must be covered. Between categories give typed edges (" + "/".join(REL_TYPES) + ") with evidence and a confidence (0-1). In each category's concepts, copy the concept names exactly as given below."
            + _fb(lang, feedback) + NL
            + "Output only JSON: " + shape
            + NL + "Concepts:" + NL + _j(concept_list))


def selective(lang, focus, categories, relations, core_examples=None, feedback=None):
    if lang == "zh":
        shape = '{"core_category":{"name":"","mapping":["范畴名"]},"theory":{"storyline":[],"propositions":[]}}'
        ref = (NL + "核心范畴命名参照（仅示意「焦点 → 核心范畴」的收敛方式，勿照抄）：" + NL + NL.join(core_examples)) if core_examples else ""
        return (PREAMBLE["zh"] + NL + "你是扎根理论选择性编码器。研究焦点 Y：" + focus + "。核心范畴必须是「关于 Y」的总纲，收敛到 Y、显式含 Y 的指称物（不自立门户）；理论是核心范畴升维出的解释框架，≠ 核心范畴名本身。"
                + NL + "选1个核心范畴（中心性+频次+连贯，非单一词频）。禁止：过度抽象成超类词（如把几个具体条件并成「制度/职业/技术」）、名字不落到具体行为（必须含具体动作动词，不能停在「实践/调适/使用」这类无动作的泛化收尾）、纯名词（黑名单：" + "/".join(BLACKLIST["zh"]) + "）。输出 JSON：" + shape + "。mapping 只列被该核心直接统摄的范畴名（用下面给出的原文范畴名；其余特异条件交给 theory.propositions 逐条列）。"
                + NL + "理论另产出：storyline=核心范畴如何统摄、编排各范畴的故事线；propositions=「核心范畴 ↔ 各范畴」的可证伪机制命题（覆盖全部特异条件——每个范畴的特异条件至少落到一条命题；按需给，不硬凑条数，非描述性复述）。"
                + ref + _fb(lang, feedback)
                + NL + "范畴：" + NL + _j(categories)
                + NL + "关系：" + NL + _j(relations))
    shape = '{"core_category":{"name":"","mapping":["category name"]},"theory":{"storyline":[],"propositions":[]}}'
    ref = (NL + "Core-category references (they only illustrate how a focus converges into a core category; do not copy):" + NL + NL.join(core_examples)) if core_examples else ""
    return (PREAMBLE["en"] + NL + "You are a grounded-theory selective coder. Research focus Y: " + focus + ". The core category must be the overall line about Y: it converges on Y and names what Y refers to (it does not set up a topic of its own). The theory is the explanatory frame raised from the core category; it is not the core category's name."
            + NL + 'Choose one core category (by centrality, frequency and coherence together, not word frequency alone). Not allowed: over-abstracting into super-class words (e.g. folding several specific conditions into "institution / profession / technology"); a name that does not land on a concrete action (it must contain a concrete action verb and must not stop at an action-less generality such as "practice", "adaptation", "use"); a bare noun (blacklist: background / strategy / preference / outcome / culture / environment). Name it in English. Output JSON: ' + shape + ". mapping lists only the categories the core category directly subsumes (use the category names exactly as given below; the remaining specific conditions go into theory.propositions one by one)."
            + NL + "The theory has two parts. storyline: how the core category subsumes and orders the categories, as a list of sentences. propositions: falsifiable mechanism propositions between the core category and each category (cover every specific condition: each category's specific condition lands in at least one proposition; as many as needed, no padding, no descriptive restating). State each so that it can fail, e.g. \"the stronger X, the more ...; if ..., the proposition is refuted\"."
            + ref + _fb(lang, feedback)
            + NL + "Categories:" + NL + _j(categories)
            + NL + "Relations:" + NL + _j(relations))


LENSES = {
    "zh": {
        "general": [
            "厚描述：不停留在「做了什么」，去看行为承载的意义结构（「意味着什么」）",
            "情境化：把对象放回其生活世界（生计、亲属关系、制度安排、在地规范）里看",
            "主位客位：同时用受访者原话（主位）与研究者位置（客位）看，分清是谁在说话",
            "意义链：看符号（物件/做法/说法）如何一环扣一环连到身份、地位、期望",
            "反思性：看清自己解读的立场与边界，承认不确定，不把单一访谈当普遍规律",
        ],
        "market": [
            "厚描述：不停留在「做了什么」，去看行为承载的意义结构（「意味着什么」）",
            "情境化：把对象放回其生活世界（收入分层、家族关系、信贷可及）里看",
            "主位客位：同时用受访者原话（主位）与研究者位置（客位）看，分清是谁在说话",
            "意义链：看符号（品牌/产品）如何一环扣一环连到身份、地位、向上流动",
            "反思性：看清自己解读的立场与边界，承认不确定，不把单一访谈当普遍规律",
        ],
    },
    "en": {
        "general": [
            "Thick description: do not stop at what was done; read the structure of meaning the behaviour carries (what it means)",
            "Contextualisation: put the people back into their life-world (livelihood, kinship, institutions, local norms)",
            "Emic and etic: read with the participants' own words (emic) and from the researcher's position (etic), and keep clear who is speaking",
            "Chain of meaning: follow how a symbol (an object, a practice, a phrase) links step by step to identity, standing and aspiration",
            "Reflexivity: be clear about the standpoint and limits of your own reading, admit uncertainty, and do not turn one interview into a general rule",
        ],
        "market": [
            "Thick description: do not stop at what was done; read the structure of meaning the behaviour carries (what it means)",
            "Contextualisation: put the people back into their life-world (income strata, family ties, access to credit)",
            "Emic and etic: read with the participants' own words (emic) and from the researcher's position (etic), and keep clear who is speaking",
            "Chain of meaning: follow how a symbol (a brand, a product) links step by step to identity, status and upward mobility",
            "Reflexivity: be clear about the standpoint and limits of your own reading, admit uncertainty, and do not turn one interview into a general rule",
        ],
    },
}
MARKET_FRAME = {
    "zh": [
        "表层·消费者行为（从文本提取可观察行为）：用户特征（人口统计/世代/心理图式/采用者）｜购买决策（触发→注意→兴趣→信息收集→购买标准→品牌考虑集→参照→权衡→成交）｜使用行为（场景/习惯/参与度/体验）｜忠诚（复购/推荐/口碑）",
        "功能层·理性需求与感知价值：功能价值（性能/可靠/耐久/服务）｜体验价值（易用/操作感/舒适）｜场景需求｜属性→利益(结果)→价值（MEC）｜感知价值＝感知利益−感知成本｜购买标准＝属性权重排序｜品牌考虑集",
    ],
    "en": [
        "Surface: consumer behaviour (observable behaviour taken from the text): user characteristics (demographics / generation / psychographics / adopter type) | purchase decision (trigger -> attention -> interest -> information search -> purchase criteria -> consideration set -> reference -> trade-off -> purchase) | usage (occasions / habits / engagement / experience) | loyalty (repurchase / recommendation / word of mouth)",
        "Functional: rational needs and perceived value: functional value (performance / reliability / durability / service) | experiential value (ease of use / feel / comfort) | occasion needs | attribute -> benefit (consequence) -> value (means-end chain) | perceived value = perceived benefits - perceived costs | purchase criteria = ranking of attribute weights | consideration set",
    ],
}


def decode(lang, lens, focus, core_name, storyline, evidence):
    lenses = LENSES[lang][lens]
    if lang == "zh":
        lens_txt = NL.join("视角" + str(i + 1) + "·" + d for i, d in enumerate(lenses))
        ev = ("证据（按范畴列出的受访者原话；引用原话只能从这里逐字摘取，不得自拟引语）：" + NL + _j(evidence)) if evidence else "（未提供原话证据：不要出现带引号的引语。）"
        shape = '{"表层":"","功能层":"","情感层":"","社会层":"","文化层":"","文化逻辑":"","象征意义":"","反例":""}'
        tail = ("情感层=主位情绪与心理动机（安全/归属/被尊重/自我认同/焦虑等）；社会层=情境化与社会价值（关系网络/群体认同/区隔）；文化层=符号价值+情境化（文化符码）；"
                "文化逻辑=意义链总纲（因果一句）；象征意义=符号的意义终点；反例=解码中发现的、与核心范畴可能矛盾或遗漏的概念/范畴（1-2 句，无则空字符串）。")
        if lens == "market":
            head = ("你是擅长商业研究的文化人类学家（商业民族志研究者），这是一项商业研究而非学术研究。研究焦点：" + focus + "。"
                    + NL + "对核心范畴「" + core_name + "」做 Geertz 厚描述解码。"
                    + NL + "五个观察视角（理解消费者的方式）：" + NL + lens_txt
                    + NL + "表层与功能层必须套用以下市场研究框架，从访谈文本提取用户及其需求、认知与行为，这两层充分展开即可（不卡比例）。若焦点是专业/B2B 场景（如从业者、专业工具），把「消费者/购买」适配为「使用者/工具采纳」，勿硬套 C 端消费话术："
                    + NL + NL.join("  " + d for d in MARKET_FRAME["zh"]))
            fields = ("字段要求：表层=厚描述（可观察的消费者行为：用户特征/购买决策/使用/忠诚，落到证据原话）；功能层=理性需求→价值转译（功能价值/体验价值/场景需求 + 感知价值：MEC/利益−成本/购买标准，落到证据原话）；" + tail)
        else:
            head = ("你是文化人类学家。研究焦点：" + focus + "。"
                    + NL + "对核心范畴「" + core_name + "」做 Geertz 厚描述解码。"
                    + NL + "五个观察视角：" + NL + lens_txt)
            fields = ("字段要求：表层=厚描述（可观察的行为：谁、在什么情境下、做了什么，落到证据原话）；功能层=这一做法替当事人解决了什么实际问题（需求、权衡与代价，落到证据原话）；" + tail)
        return (head + NL + "只输出 JSON（8 个平铺字段）：" + shape + NL + fields
                + NL + "故事线：" + _j(storyline) + NL + ev)
    lens_txt = NL.join("Lens " + str(i + 1) + ". " + d for i, d in enumerate(lenses))
    ev = ("Evidence (participants' own words, listed by category; quote only from here, verbatim, and never invent a quotation):" + NL + _j(evidence)) if evidence else "(No verbatim evidence was provided: do not write anything inside quotation marks.)"
    shape = '{"surface":"","functional":"","emotional":"","social":"","cultural":"","cultural_logic":"","symbolic_meaning":"","counter_example":""}'
    tail = ("emotional = emic feelings and motives (safety / belonging / being respected / self-identity / anxiety and the like); social = contextualisation and social value (networks / group identity / distinction); cultural = symbolic value in context (cultural codes); "
            "cultural_logic = the chain of meaning in one causal sentence; symbolic_meaning = where the symbol's meaning ends up; counter_example = concepts or categories met while decoding that may contradict the core category or be missing from it (1-2 sentences; empty string if none).")
    if lens == "market":
        head = ("You are a cultural anthropologist who works on commercial research (a business ethnographer). This is commercial research, not academic research. Research focus: " + focus + "."
                + NL + "Give a thick-description (Geertz) decoding of the core category «" + core_name + "»."
                + NL + "Five lenses (ways of understanding the consumer):" + NL + lens_txt
                + NL + "The surface and functional layers must use the market-research frame below to take users, their needs, perceptions and behaviour from the interview text; develop these two layers fully. If the focus is a professional or B2B setting (practitioners, professional tools), read \"consumer / purchase\" as \"user / tool adoption\" and do not force consumer vocabulary onto it:"
                + NL + NL.join("  " + d for d in MARKET_FRAME["en"]))
        fields = ("Fields: surface = thick description (observable consumer behaviour: user characteristics / purchase decision / usage / loyalty, tied to the evidence); functional = rational needs translated into value (functional value / experiential value / occasion needs + perceived value: means-end chain / benefits minus costs / purchase criteria, tied to the evidence); " + tail)
    else:
        head = ("You are a cultural anthropologist. Research focus: " + focus + "."
                + NL + "Give a thick-description (Geertz) decoding of the core category «" + core_name + "»."
                + NL + "Five lenses:" + NL + lens_txt)
        fields = ("Fields: surface = thick description (observable behaviour: who does what in which situation, tied to the evidence); functional = what practical problem this way of acting solves for the people involved (needs, trade-offs and costs, tied to the evidence); " + tail)
    return (head + NL + "Output only JSON (8 flat fields): " + shape + NL + fields
            + NL + "Storyline: " + _j(storyline) + NL + ev)


def ib_semantic(lang, core_name, storyline, cat_info):
    """Telemetry: the model's own estimate of how much each category contributes to the core category."""
    if lang == "zh":
        return ("你是消融贡献评估器：评估每个范畴对核心范畴的信息贡献（0-1）。"
                + NL + "核心范畴（Y）：" + core_name
                + NL + "故事线：" + _j(storyline)
                + NL + "对每个范畴判断它对核心范畴的「信息贡献」（0-1，消融评分）：删掉该范畴，核心故事线会损失多少信息。0=无关可删，1=核心支柱不可缺。"
                + NL + '只输出 JSON 数组：[{"name":"范畴名","contribution":0.5}]，覆盖所有范畴，contribution 是 0 到 1 的数字。'
                + NL + "范畴列表：" + _j(cat_info))
    return ("You estimate ablation contributions: how much information each category contributes to the core category (0-1)."
            + NL + "Core category (Y): " + core_name
            + NL + "Storyline: " + _j(storyline)
            + NL + "For each category, judge its information contribution to the core category (0-1, an ablation score): how much the core storyline would lose if the category were removed. 0 = unrelated, can be removed; 1 = a pillar that cannot be missing."
            + NL + 'Output only a JSON array: [{"name":"category name","contribution":0.5}], covering every category; contribution is a number from 0 to 1.'
            + NL + "Categories: " + _j(cat_info))


def decode_selfscore(lang, decode_out):
    """Telemetry: the model's own 1-5 rating of the decoding on the five lenses."""
    if lang == "zh":
        return ("你是文化解码评估者。按 1-5 对以下解码输出打分（1=去情境口号/刻板；3=部分；5=人类学家级/Geertz 厚度）："
                + NL + "五维：厚描述、情境化、主位客位、意义链、反思性。"
                + NL + '只输出 JSON：{"厚描述":4,"情境化":4,"主位客位":4,"意义链":4,"反思性":4}'
                + NL + "解码输出：" + _j(decode_out)[:3000])
    return ("You assess a cultural decoding. Rate the output below from 1 to 5 (1 = decontextualised slogan or stereotype; 3 = partial; 5 = anthropologist-level, Geertzian thickness)."
            + NL + "Five dimensions: thick_description, contextualisation, emic_etic, chain_of_meaning, reflexivity."
            + NL + 'Output only JSON: {"thick_description":4,"contextualisation":4,"emic_etic":4,"chain_of_meaning":4,"reflexivity":4}'
            + NL + "Decoding: " + _j(decode_out)[:3000])


def reflexive(lang, n_labels, n_concepts, n_cats, coder):
    """The M block: boundary, position and uncertainty of the analysis, stated by the program, not by a model."""
    if lang == "zh":
        return {"boundary": ["压缩了 %d 语义标签 -> %d 概念 -> %d 范畴" % (n_labels, n_concepts, n_cats)],
                "position": ["概括基于 %d 个语义标签（主位原话，开放编码模型：%s）+ LLM 二、三级编码（客位范畴）" % (n_labels, coder)],
                "uncertainty": ["核心范畴由统摄度最高选出（非频次）；语义边界与反例需人工复核"]}
    return {"boundary": ["compressed %d semantic labels -> %d concepts -> %d categories" % (n_labels, n_concepts, n_cats)],
            "position": ["built on %d semantic labels in the participants' own words (open-coding model: %s) plus model-made concepts and categories (etic)" % (n_labels, coder)],
            "uncertainty": ["the core category is the one that subsumes most (not the most frequent); semantic boundaries and counter-examples need human review"]}


FEEDBACK = {
    "zh": {"open_failed": "开放编码失败", "concepts_failed": "概念化失败",
           "fidelity": "保真不足：让每个概念都被某范畴吸收", "paradigm": "六要素不完备：6C 槽位须全覆盖",
           "specific": "特异性低：概念名缺特异修饰词，补人群/条件/机制修饰", "absorb": "标签吸收率低：更多语义标签应被概念吸收",
           "counter": "E解码反例："},
    "en": {"open_failed": "open coding failed", "concepts_failed": "concept coding failed",
           "fidelity": "low fidelity: every concept should be absorbed by some category",
           "paradigm": "paradigm incomplete: all six 6C slots must be covered",
           "specific": "low specificity: concept names lack specific modifiers; add who / condition / mechanism",
           "absorb": "low label absorption: more semantic labels should be absorbed by concepts",
           "counter": "counter-example from decoding: "},
}
DECODE_MARKER = {"zh": "（解码回馈）", "en": "(from decoding) "}
