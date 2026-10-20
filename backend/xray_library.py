"""Vetted X-ray recognition library. Each entry pairs a realistic radiograph with a
clinically-correct recognition question, options and explanation (TR/EN).
Both authored cases and LLM-generated cases reference these by id, so X-ray facts
are always clinically correct regardless of the LLM."""

BASE = "/xray/"

XRAY_LIB = {
    "deep_filling_pulp": {
        "image": BASE + "5f0de1290fac177974f999fa81ef9c189a6185f62d49e84ebaf1664262593485.jpeg",
        "finding_en": "Deep restoration very close to the pulp",
        "options": [
            {"id": "deep_filling", "correct": True, "label": {"tr": "Pulpaya çok yakın derin restorasyon", "en": "Deep restoration very close to the pulp"}},
            {"id": "periapical", "correct": False, "label": {"tr": "Apikal radyolusensi (apse)", "en": "Periapical radiolucency (abscess)"}},
            {"id": "fracture", "correct": False, "label": {"tr": "Dikey kök kırığı", "en": "Vertical root fracture"}},
            {"id": "normal", "correct": False, "label": {"tr": "Herhangi bir patoloji yok", "en": "No pathology"}},
        ],
        "explanation": {
            "tr": "Kuronda pulpa boynuzuna dayanan büyük radyoopak restorasyona bakın. Apekste koyu radyolusensi yok ve periodontal aralık korunmuş — bu, pulpaya yakın derin restorasyonu düşündürür, henüz apikal patoloji yoktur.",
            "en": "Look for the large radiopaque restoration in the crown sitting on the pulp horn. There is no dark apical radiolucency and the periodontal space is intact — pointing to a deep restoration close to the pulp, without apical pathology yet.",
        },
    },
    "periapical_lesion": {
        "image": BASE + "029aacf39c4d943cc6576df681bdb7b7db08d42088aca6a9370eb189b968af52.jpeg",
        "finding_en": "Well-defined periapical radiolucency (lesion)",
        "options": [
            {"id": "periapical", "correct": True, "label": {"tr": "Apeksde iyi sınırlı radyolusensi (lezyon)", "en": "Well-defined periapical radiolucency (lesion)"}},
            {"id": "deep_filling", "correct": False, "label": {"tr": "Pulpaya yakın derin dolgu", "en": "Deep filling near the pulp"}},
            {"id": "impaction", "correct": False, "label": {"tr": "Gömük diş", "en": "Impacted tooth"}},
            {"id": "normal", "correct": False, "label": {"tr": "Herhangi bir patoloji yok", "en": "No pathology"}},
        ],
        "explanation": {
            "tr": "Kök ucunda (apeks) yuvarlak, koyu (radyolusent), iyi sınırlı bir alan ve çevresinde kemik kaybı arayın. Bu, nekrotik pulpaya bağlı kronik apikal enfeksiyonun (apse/granülom) tipik görüntüsüdür.",
            "en": "Look for a round, dark (radiolucent), well-defined area at the root tip (apex) with surrounding bone loss — the classic look of a chronic apical infection (abscess/granuloma) from a necrotic pulp.",
        },
    },
    "normal_bitewing": {
        "image": BASE + "d0ba96fd403282cea0a39c2e19e5177eef89d1e6021797ac6e382e0c95e12ae1.jpeg",
        "finding_en": "No caries or bone loss (normal)",
        "options": [
            {"id": "normal", "correct": True, "label": {"tr": "Çürük veya kemik kaybı yok (normal)", "en": "No caries or bone loss (normal)"}},
            {"id": "caries", "correct": False, "label": {"tr": "İnterproksimal çürük", "en": "Interproximal caries"}},
            {"id": "periapical", "correct": False, "label": {"tr": "Apikal radyolusensi", "en": "Periapical radiolucency"}},
            {"id": "bone_loss", "correct": False, "label": {"tr": "İleri kemik kaybı", "en": "Advanced bone loss"}},
        ],
        "explanation": {
            "tr": "Dişler arası (interproksimal) yüzeylerde koyu üçgen çürük gölgesi ve alveol kemiği tepesinde kayıp olup olmadığına bakın. Burada mineler sağlam ve kemik seviyeleri normaldir.",
            "en": "Check interproximal surfaces for dark triangular decay shadows and the bone crest for loss. Here enamel is intact and bone levels are normal.",
        },
    },
    "impacted_wisdom": {
        "image": BASE + "3322129b59230fbde9574ad9c67c2083625533fcc4b4b4e0f1b63f52c671cad7.jpeg",
        "finding_en": "Mesioangular impacted wisdom tooth",
        "options": [
            {"id": "impaction", "correct": True, "label": {"tr": "Mesioanguler gömük 20 yaş dişi", "en": "Mesioangular impacted wisdom tooth"}},
            {"id": "periapical", "correct": False, "label": {"tr": "Komşu dişte apikal apse", "en": "Apical abscess on the adjacent tooth"}},
            {"id": "caries", "correct": False, "label": {"tr": "İkinci molarda derin çürük", "en": "Deep caries in the second molar"}},
            {"id": "normal", "correct": False, "label": {"tr": "Normal sürmüş diş", "en": "Normally erupted tooth"}},
        ],
        "explanation": {
            "tr": "En arkadaki 20 yaş dişinin öne (mesial) eğilerek komşu ikinci molara dayandığına bakın — bu mesioanguler gömüklüktür.",
            "en": "See how the rearmost wisdom tooth tilts forward (mesially) and is impacted against the adjacent second molar — mesioangular impaction.",
        },
    },
    "interproximal_caries": {
        "image": BASE + "3247b11271b5238442bc3a04f6cecdd0063f1ae5731ee1242613effafdc0b40e.jpeg",
        "finding_en": "Interproximal caries",
        "options": [
            {"id": "caries", "correct": True, "label": {"tr": "İnterproksimal (dişler arası) çürük", "en": "Interproximal (between-teeth) caries"}},
            {"id": "normal", "correct": False, "label": {"tr": "Çürük yok (normal)", "en": "No caries (normal)"}},
            {"id": "periapical", "correct": False, "label": {"tr": "Apikal radyolusensi", "en": "Periapical radiolucency"}},
            {"id": "calculus", "correct": False, "label": {"tr": "Diş taşı birikimi", "en": "Calculus deposits"}},
        ],
        "explanation": {
            "tr": "İki diş arasında minede başlayan koyu, üçgen şeklinde radyolusent gölge çürüğü gösterir. Kenarları ve derinliğini değerlendirin.",
            "en": "A dark, triangular radiolucent shadow starting in the enamel between two teeth indicates caries. Assess its margins and depth.",
        },
    },
    "bone_loss": {
        "image": BASE + "56d8d8083388e69ce24aaf3c0792ede022e5cacf636ec9634e749220ea45f6aa.jpeg",
        "finding_en": "Horizontal alveolar bone loss (periodontitis)",
        "options": [
            {"id": "bone_loss", "correct": True, "label": {"tr": "Horizontal alveolar kemik kaybı (periodontitis)", "en": "Horizontal alveolar bone loss (periodontitis)"}},
            {"id": "normal", "correct": False, "label": {"tr": "Normal kemik seviyeleri", "en": "Normal bone levels"}},
            {"id": "caries", "correct": False, "label": {"tr": "İnterproksimal çürük", "en": "Interproximal caries"}},
            {"id": "impaction", "correct": False, "label": {"tr": "Gömük diş", "en": "Impacted tooth"}},
        ],
        "explanation": {
            "tr": "Alveol kemik tepesinin mine-sement sınırının belirgin şekilde altına indiğine ve dişler boyunca kemik seviyesinin düştüğüne bakın — bu kronik periodontitisi gösterir.",
            "en": "Note how the alveolar bone crest sits well below the cemento-enamel junction and drops along the teeth — indicating chronic periodontitis.",
        },
    },
    "root_fracture": {
        "image": BASE + "ed93fa4fd40c3e2ad281f8d80fa317c98e57f4e8d4b18bd4f92f1b521a18a9a0.jpeg",
        "finding_en": "Vertical root fracture",
        "options": [
            {"id": "fracture", "correct": True, "label": {"tr": "Dikey kök kırığı", "en": "Vertical root fracture"}},
            {"id": "normal", "correct": False, "label": {"tr": "Sağlam kök (normal)", "en": "Intact root (normal)"}},
            {"id": "periapical", "correct": False, "label": {"tr": "Apikal radyolusensi", "en": "Periapical radiolucency"}},
            {"id": "deep_filling", "correct": False, "label": {"tr": "Pulpaya yakın derin dolgu", "en": "Deep filling near the pulp"}},
        ],
        "explanation": {
            "tr": "Kök boyunca uzanan ince radyolusent kırık hattını ve kırık çevresinde artmış radyolusensiyi arayın — dikey kök kırığının tipik bulgusu.",
            "en": "Look for a thin radiolucent fracture line running down the root with surrounding radiolucency — typical of a vertical root fracture.",
        },
    },
    "retained_root": {
        "image": BASE + "8d7864dc6beeccce4004d65d4c7db327203b3162277ccb52ffade0e6e54620a7.jpeg",
        "finding_en": "Retained root tip",
        "options": [
            {"id": "retained_root", "correct": True, "label": {"tr": "Artık kök (retained root tip)", "en": "Retained root tip"}},
            {"id": "impaction", "correct": False, "label": {"tr": "Gömük diş", "en": "Impacted tooth"}},
            {"id": "normal", "correct": False, "label": {"tr": "Normal (patoloji yok)", "en": "Normal (no pathology)"}},
            {"id": "periapical", "correct": False, "label": {"tr": "Apikal radyolusensi", "en": "Periapical radiolucency"}},
        ],
        "explanation": {
            "tr": "Kuronu olmayan, kemik içinde kalmış kök parçasına (artık kök) bakın. Çevre kemiği ve enfeksiyon belirtisi olup olmadığını değerlendirin.",
            "en": "Look for a root fragment left in the bone with no crown (retained root). Assess the surrounding bone for any sign of infection.",
        },
    },
    "root_canal_filled": {
        "image": BASE + "a74a8706b84c6277fe6727c77bacebbc3cb1948aeb0be3d5eb802b9ec6e0f3fe.jpeg",
        "finding_en": "Completed root canal filling",
        "options": [
            {"id": "rct_filled", "correct": True, "label": {"tr": "Tamamlanmış kök kanal dolgusu", "en": "Completed root canal filling"}},
            {"id": "periapical", "correct": False, "label": {"tr": "Apikal radyolusensi", "en": "Periapical radiolucency"}},
            {"id": "fracture", "correct": False, "label": {"tr": "Kök kırığı", "en": "Root fracture"}},
            {"id": "caries", "correct": False, "label": {"tr": "Derin çürük", "en": "Deep caries"}},
        ],
        "explanation": {
            "tr": "Kök kanallarını dolduran yoğun radyoopak materyale ve üzerindeki restorasyona bakın — daha önce kanal tedavisi yapılmış bir diştir. Apeksde lezyon olup olmadığını kontrol edin.",
            "en": "Look for the dense radiopaque material filling the canals and the overlying restoration — a previously root-canal-treated tooth. Check the apex for any lesion.",
        },
    },
    "widened_pdl": {
        "image": BASE + "24fc6aff357eb6893c10c2f7cbda4bf56175fa8eab1a0a88947beb1fdf379923.jpeg",
        "finding_en": "Widened periodontal ligament space (early apical change)",
        "options": [
            {"id": "widened_pdl", "correct": True, "label": {"tr": "Genişlemiş periodontal aralık (erken apikal değişiklik)", "en": "Widened periodontal ligament space (early apical change)"}},
            {"id": "normal", "correct": False, "label": {"tr": "Normal periapikal aralık", "en": "Normal periapical space"}},
            {"id": "fracture", "correct": False, "label": {"tr": "Kök kırığı", "en": "Root fracture"}},
            {"id": "impaction", "correct": False, "label": {"tr": "Gömük diş", "en": "Impacted tooth"}},
        ],
        "explanation": {
            "tr": "Kök ucunda periodontal ligament aralığının genişlediğine ve lamina durada kalınlaşmaya bakın; henüz büyük bir radyolusensi yoktur — erken/başlangıç apikal periodontitis.",
            "en": "Note the widened periodontal ligament space at the apex and thickened lamina dura, without a large radiolucency yet — early apical periodontitis.",
        },
    },
}


def xray_public(lib_id, lang):
    """Spoiler-free X-ray payload for the client (no correct flag)."""
    e = XRAY_LIB.get(lib_id)
    if not e:
        return None
    q = {"tr": "Bu radyografideki ana bulgu nedir?", "en": "What is the main finding on this radiograph?"}
    return {
        "image": e["image"],
        "question": q[lang if lang in q else "tr"],
        "options": [{"id": o["id"], "label": o["label"].get(lang, o["label"]["tr"])} for o in e["options"]],
    }
