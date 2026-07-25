"""Feynman gate — judge prose against the pedagogical standard of the Feynman Lectures.

Standalone experiment (NOT wired into the rite). One function: feynman_gate.
Pure LLM judgment — no keyword matching.
"""
import json
import re

RUBRIC = """\
You are judging prose against the pedagogical standard of *The Feynman Lectures on Physics*.
The bar (each is a real, testable quality of that book):

1. FIRST PRINCIPLES / INTUITION FIRST — builds understanding from the ground up; the idea
   is motivated before it is used.
2. NO UNEXPLAINED REFERENT — every term, name, jargon word, slug (e.g. `#foo-bar`), date-code,
   ULID, ticket id, or internal handle is NAMED AND EXPLAINED. A reader who did NOT live the
   session can still follow it. A bare `#slug`, a bare date like "07-13", or a raw ID with no
   gloss is a defect.
3. CONTEXTUALIZE THE NEW, ASSUME ONLY THE SHARED — what is genuinely new is explained; only
   what is truly common knowledge is assumed. Not condescending, not cryptic.
4. CONCRETE BEFORE ABSTRACT — a concrete instance grounds each abstraction.
5. OUTSIDER-FOLLOWABLE — an intelligent outsider hungry for context can reconstruct the
   argument without a glossary they don't have.
6. HONEST ABOUT THE UNKNOWN — states plainly what is not known or not decided.

Judge ONLY clarity/pedagogy against this bar. Do NOT judge whether the subject is worth writing
about — assume the subject is legitimate. The failure mode you hunt is: text that assumes the
reader lived the session.

Return STRICT JSON, nothing else, in this exact shape:
{
  "passa": <true|false>,           // true only if a context-hungry outsider could follow it
  "score_0_10": <int 0-10>,        // 10 = Feynman-clear, 0 = fully cryptic/insider-only
  "gaps": [<string>, ...],         // each a CONCRETE, ACTIONABLE clarity defect, e.g.
                                   //   "term 'X' used but never defined for a reader not in the session"
                                   //   "bare slug `#foo` cited with no gloss of what it names"
  "veredito": <string>             // one-sentence overall read
}
Every gap must point to a specific defect in THIS text. If it is already clear, gaps is [].
pass threshold: passa=true iff score_0_10 >= 7.
"""


def feynman_gate(text, complete_fn):
    """Judge `text` against the Feynman-Lectures clarity bar via an LLM.

    Returns {"passa": bool, "score_0_10": int, "gaps": [str], "veredito": str}.
    """
    prompt = f"{RUBRIC}\n\n=== TEXT TO JUDGE ===\n{text}\n=== END TEXT ===\n\nReturn ONLY the JSON object."
    raw = complete_fn(prompt)
    return _parse(raw)


def _parse(raw):
    # models often fence the JSON or add prose; grab the outermost {...}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in judge output: {raw[:300]!r}")
    obj = json.loads(m.group(0))
    return {
        "passa": bool(obj.get("passa", obj.get("score_0_10", 0) >= 7)),
        "score_0_10": int(obj.get("score_0_10", 0)),
        "gaps": list(obj.get("gaps", [])),
        "veredito": str(obj.get("veredito", "")),
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "tools")
    import llm_routes

    def complete(prompt, route="review", max_tokens=4000):
        return llm_routes.completer_for(route, max_tokens=max_tokens)(prompt)

    clear = (
        "A cache stores the answer to a question so you don't have to compute it twice. "
        "For example, if adding 2+2 were slow, you'd write '4' on a sticky note and read the "
        "note next time instead of adding again. Our system does the same with database queries: "
        "the first request runs the query and saves the result; later identical requests read the "
        "saved result. The tradeoff is staleness — if the underlying data changes, the note is wrong "
        "until we tear it up."
    )
    cryptic = (
        "The residual after Pauta is #foo-bar-baz, not the anti-X org. The 07-13 patch holds until "
        "ULID 01KYBTM triggers the S5 threshold; until then, park. Q1 not Q4, per the knows-years "
        "dogfood n=1. The fork is who he is under ticket pressure."
    )
    c = feynman_gate(clear, complete)
    x = feynman_gate(cryptic, complete)
    print("clear  :", c)
    print("cryptic:", x)
    assert c["score_0_10"] > x["score_0_10"], "clear text must score higher than cryptic"
    print("SELF-CHECK PASS: clear", c["score_0_10"], ">", x["score_0_10"], "cryptic")


# A LENTE do final_review (fiada pelo rito em TODO fecho — a régua das Lectures como
# critério de strike pedagógico). Contrapesos VINCULANTES no próprio texto:
# correção factual é do fact-audit; crescimento não é defeito — enchimento é.
LENS_BLOCK = """\
=== LENTE LECTURES-ON-PHYSICS (parte integrante desta revisão) ===
Julgue TAMBÉM a clareza pedagógica do texto contra a régua das *Feynman Lectures on
Physics*: intuição/primeiros princípios antes do uso; NENHUM referente sem nome e sem
glosa (termo, slug, id, data-código — tudo explicado para um leitor que NÃO viveu a
sessão); o novo contextualizado; o concreto ancorando cada abstração; um outsider
inteligente consegue reconstruir o argumento; honestidade explícita sobre o que não se
sabe. Um defeito CONCRETO de clareza (referente sem nome, rótulo sem mecanismo, texto
que assume que o leitor viveu a sessão) é STRIKE como qualquer outro strike desta
revisão.

Contrapesos vinculantes desta lente:
1. Ela julga se um leitor de fora consegue SEGUIR — correção factual pertence ao
   fact-audit (estágio próprio); não re-julgue fatos aqui.
2. Comprimento NÃO é defeito: enriquecimento pedagógico cresce por natureza. O strike é
   para ENCHIMENTO — prosa que não adiciona entendimento por palavra (repetição, rótulo
   re-embalado, cerimônia) — nunca para o texto ter ficado maior.
"""
