# Qualtrics JavaScript reference — ICJ expert elicitation survey

**Last consolidated:** September 2026  
**Chat:** Qualtrics JS for Q16, Q24, Q13, Q15, Q10, Q35

This document summarises the **latest working code** from that build session. Replace `QID16`, `QID24`, `QID13`, `QID15`, `QID10`, `QID35` with your actual question IDs if they differ.

---

## Survey flow (question order)

```
Q16 (UK share %)
  → … earlier Part 1 questions …
  → Q24 + Q13 (same page)
  → [page break]
  → Q15 (Part 1 check your work)
  → Q25 (Part 2 intro, text only)
  → Q10 (+ optional justification on same page)
  → [page break]
  → Q35 (Part 2 check your work)
  → justification / follow-up
```

---

## New Survey Taking Experience — rules

| Rule | Detail |
|------|--------|
| JS API | Use `setJSEmbeddedData` / `getJSEmbeddedData` (not `setEmbeddedData`) |
| Survey Flow names | JS-written fields need `__js_` prefix in Survey Flow (e.g. `__js_uk_share`) |
| In JavaScript | Call fields **without** prefix: `"uk_share"`, `"damages_median"` |
| GDP constants | Set in Survey Flow with **Set a value now** — no `__js_` prefix |
| Q15 / Q35 display | Use `this.getQuestionContainer()` — do not rely on `#QID15` selectors |
| Publish | Required after every JavaScript change |

---

## Survey Flow — constants (Set a value now)

| Field | Value |
|-------|-------|
| `pakistan_gdp_bn` | `408` |
| `uk_gdp_bn` | `3786` |
| `cvc_gdp_bn` | `4100` |

---

## Survey Flow — blank `__js_` fields

**Part 1 (Q13):**  
`__js_uk_share`, `__js_uk_share_label`, `__js_uk_share_pct`  
`__js_damages_lower`, `__js_damages_median`, `__js_damages_upper`  
`__js_pct_damages_gdp_lower`, `__js_pct_damages_gdp_median`, `__js_pct_damages_gdp_upper`  
`__js_pak_award_lower`, `__js_pak_award_median`, `__js_pak_award_upper`  
`__js_pct_pak_gdp_lower`, `__js_pct_pak_gdp_median`, `__js_pct_pak_gdp_upper`  
`__js_pct_uk_gdp_lower`, `__js_pct_uk_gdp_median`, `__js_pct_uk_gdp_upper`

**Part 2 (Q10):**  
`__js_scaling_lower`, `__js_scaling_median`, `__js_scaling_upper`  
`__js_cvf_damages_proxy`, `__js_damages_median_display`, `__js_pct_damages_gdp_median_display`  
`__js_cvf_flow_lower`, `__js_cvf_flow_median`, `__js_cvf_flow_upper`  
`__js_cvf_pct_gdp_lower`, `__js_cvf_pct_gdp_median`, `__js_cvf_pct_gdp_upper`  
`__js_uk_cvf_lower`, `__js_uk_cvf_median`, `__js_uk_cvf_upper`  
`__js_pct_uk_cvf_lower`, `__js_pct_uk_cvf_median`, `__js_pct_uk_cvf_upper`

---

## Form field order (Q24 and Q10)

| Index | Field |
|-------|--------|
| 0 | Lower bound (1%) |
| 1 | Upper bound (99%) |
| 2 | Median / central (50%) |

---

## Formulas

**Part 1 (Q13)**  
- `pak_award = uk_share × damages` (uk_share stored as **decimal**, e.g. 0.025)  
- `% GDP = award or damages ÷ GDP × 100`

**Part 2 (Q10)**  
- `cvf_proxy = damages_median × (cvc_gdp / pakistan_gdp)`  
- `cvf_flow = cvf_proxy × scaling`  
- `uk_cvf = cvf_flow × uk_share`  
- Display values rounded via `roundBn` / `roundPct`; `uk_share_pct` always **1 dp**

---

# Q16 — UK share (text entry %)

**Hook:** `addOnPageSubmit`  
**Question type:** Text entry (user enters e.g. `1.9` for 1.9%)

```javascript
Qualtrics.SurveyEngine.addOnPageSubmit(function saveUkShare() {
    var raw = "";
    try {
        raw = this.getQuestionValue().getValue();
    } catch (e) {}

    var pct = parseFloat(String(raw).trim());

    if (isNaN(pct)) {
        var container = document.querySelector("#question-QID16") || document.querySelector("#QID16");
        if (container) {
            var inp = container.querySelector("input[type='text'], input[type='number'], input.text-input");
            if (inp && inp.value.trim() !== "") pct = parseFloat(inp.value.trim());
        }
    }

    if (isNaN(pct)) {
        alert("Please enter the UK's share as a percentage (e.g. 1.9 for 1.9%).");
        return false;
    }
    if (pct <= 0 || pct > 100) {
        alert("Please enter a number between 0 and 100 (e.g. 1.9 for 1.9%).");
        return false;
    }

    var share = pct / 100;
    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_share", String(share));
    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_share_pct", pct.toFixed(1));
    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_share_label", "Expert estimate: " + pct + "%");

    return true;
});
```

---

# Q24 — damages validation only

**Hook:** `Validate Response` (in JavaScript modal) **or** Response requirements → Custom validation  
**Do not** put calculation script on Q24.

```javascript
var values = this.getQuestionValue().getValues();
var lower = parseFloat(values[0]);
var upper = parseFloat(values[1]);
var median = parseFloat(values[2]);

if (isNaN(lower) || isNaN(upper) || isNaN(median)) {
    alert("Please enter numbers for all three fields.");
    return false;
}
if (median <= lower) {
    alert("Your central estimate must be greater than your lower bound.");
    return false;
}
if (median >= upper) {
    alert("Your central estimate must be less than your upper bound.");
    return false;
}
```

---

# Q13 — Part 1 calculation

**Hook:** `addOnPageSubmit`  
**Same page as Q24** — reads Q24 inputs from DOM; reads Q16 share via piped text.

```javascript
Qualtrics.SurveyEngine.addOnPageSubmit(function () {
    var container = document.querySelector("#question-QID24") || document.querySelector("#QID24");
    if (!container) return true;

    var inputs = container.querySelectorAll("input.text-input, input[type='text'], input[type='number']");
    if (inputs.length < 3) return true;

    var lower = parseFloat(inputs[0].value);
    var upper = parseFloat(inputs[1].value);
    var median = parseFloat(inputs[2].value);

    var sharePct = parseFloat("${q://QID16/ChoiceTextEntryValue}");
    var share = isNaN(sharePct)
        ? parseFloat(Qualtrics.SurveyEngine.getJSEmbeddedData("uk_share"))
        : sharePct / 100;

    var shareLabel = isNaN(sharePct)
        ? Qualtrics.SurveyEngine.getJSEmbeddedData("uk_share_label")
        : "Expert estimate: " + sharePct + "%";

    if (isNaN(lower) || isNaN(upper) || isNaN(median) || isNaN(share)) return true;

    var pakGdp = parseFloat(Qualtrics.SurveyEngine.getEmbeddedData("pakistan_gdp_bn")) || 408;
    var ukGdp  = parseFloat(Qualtrics.SurveyEngine.getEmbeddedData("uk_gdp_bn")) || 3786;

    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_share", String(share));
    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_share_pct", (share * 100).toFixed(1));
    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_share_label", shareLabel);

    Qualtrics.SurveyEngine.setJSEmbeddedData("damages_lower", String(lower));
    Qualtrics.SurveyEngine.setJSEmbeddedData("damages_median", String(median));
    Qualtrics.SurveyEngine.setJSEmbeddedData("damages_upper", String(upper));

    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_damages_gdp_lower",  ((lower  / pakGdp) * 100).toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_damages_gdp_median", ((median / pakGdp) * 100).toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_damages_gdp_upper",  ((upper  / pakGdp) * 100).toFixed(2));

    var awardLower  = share * lower;
    var awardMedian = share * median;
    var awardUpper  = share * upper;

    Qualtrics.SurveyEngine.setJSEmbeddedData("pak_award_lower",  awardLower.toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pak_award_median", awardMedian.toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pak_award_upper",  awardUpper.toFixed(2));

    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_pak_gdp_lower",  ((awardLower  / pakGdp) * 100).toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_pak_gdp_median", ((awardMedian / pakGdp) * 100).toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_pak_gdp_upper",  ((awardUpper  / pakGdp) * 100).toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_uk_gdp_lower",   ((awardLower  / ukGdp) * 100).toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_uk_gdp_median",  ((awardMedian / ukGdp) * 100).toFixed(2));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_uk_gdp_upper",   ((awardUpper  / ukGdp) * 100).toFixed(2));

    return true;
});
```

**If share pipe fails:** try `${q://QID16/ChoiceNumericEntryValue}` instead.

---

# Q15 — Part 1 check your work

**Question text:** paste HTML below in **HTML view** (or keep minimal text if using JS-only display).  
**Hook:** `addOnReady`

## Q15 — HTML

```html
<p><strong>Check your work &mdash; implied compensation award for Pakistan from UK in first contentious case</strong></p>

<p>You indicated total financially assessable damages to Pakistan from climate change (from all states) of:</p>

<ul>
  <li>Lower bound: <strong><span id="ed_damages_lower"></span></strong> billion USD (<strong><span id="ed_pct_damages_gdp_lower"></span>%</strong> of Pakistan GDP)</li>
  <li>Central estimate: <strong><span id="ed_damages_median"></span></strong> billion USD (<strong><span id="ed_pct_damages_gdp_median"></span>%</strong> of Pakistan GDP)</li>
  <li>Upper bound: <strong><span id="ed_damages_upper"></span></strong> billion USD (<strong><span id="ed_pct_damages_gdp_upper"></span>%</strong> of Pakistan GDP)</li>
</ul>

<p>UK&#39;s share of internationally wrongful climate harm: <strong><span id="ed_uk_share_pct"></span></strong></p>

<p>Implied UK compensation award to Pakistan:</p>

<ul>
  <li>Lower: <strong><span id="ed_pak_award_lower"></span></strong> billion USD</li>
  <li>Central estimate: <strong><span id="ed_pak_award_median"></span></strong> billion USD</li>
  <li>Upper: <strong><span id="ed_pak_award_upper"></span></strong> billion USD</li>
</ul>

<p>Implied award as a share of GDP (2025 nominal GDP: UK $3,786bn; Pakistan $408bn):</p>

<ul>
  <li>Central estimate: <strong><span id="ed_pct_uk_gdp_median"></span>%</strong> of UK GDP; <strong><span id="ed_pct_pak_gdp_median"></span>%</strong> of Pakistan GDP</li>
  <li><em>Range across your lower&ndash;upper award: UK <span id="ed_pct_uk_gdp_lower"></span>&ndash;<span id="ed_pct_uk_gdp_upper"></span>%; Pakistan <span id="ed_pct_pak_gdp_lower"></span>&ndash;<span id="ed_pct_pak_gdp_upper"></span>%.</em></li>
</ul>

<p><strong>Does this outcome look plausible for a hypothetical first ICJ climate compensation case?</strong><br />
If you want to change any answers, click <strong>Previous page</strong> now.</p>
```

**Note:** `ed_uk_share_pct` value should be numeric only (e.g. `2.3`) — no `%` in the stored value or you get `%%`.

## Q15 — JavaScript

```javascript
Qualtrics.SurveyEngine.addOnReady(function () {
    var host = this.getQuestionContainer();
    if (!host) return;

    function setText(id, key) {
        var el = host.querySelector("#" + id) || document.getElementById(id);
        if (!el) return;
        var val = Qualtrics.SurveyEngine.getJSEmbeddedData(key);
        el.textContent = (val !== null && val !== undefined && val !== "") ? val : "—";
    }

    setText("ed_damages_lower",          "damages_lower");
    setText("ed_damages_median",         "damages_median");
    setText("ed_damages_upper",          "damages_upper");
    setText("ed_pct_damages_gdp_lower",  "pct_damages_gdp_lower");
    setText("ed_pct_damages_gdp_median", "pct_damages_gdp_median");
    setText("ed_pct_damages_gdp_upper",  "pct_damages_gdp_upper");
    setText("ed_uk_share_pct",           "uk_share_pct");
    setText("ed_pak_award_lower",        "pak_award_lower");
    setText("ed_pak_award_median",       "pak_award_median");
    setText("ed_pak_award_upper",        "pak_award_upper");
    setText("ed_pct_uk_gdp_lower",       "pct_uk_gdp_lower");
    setText("ed_pct_uk_gdp_median",      "pct_uk_gdp_median");
    setText("ed_pct_uk_gdp_upper",       "pct_uk_gdp_upper");
    setText("ed_pct_pak_gdp_lower",      "pct_pak_gdp_lower");
    setText("ed_pct_pak_gdp_median",     "pct_pak_gdp_median");
    setText("ed_pct_pak_gdp_upper",      "pct_pak_gdp_upper");
});
```

---

# Q10 — scaling validation + calculation

**Hook:** two `addOnPageSubmit` blocks on Q10 (or last question before Q35 page break).  
**Response requirements:** Request response **OFF** (optional skip allowed).

## Q10 — Block 1: validateScalingFactorBounds

```javascript
Qualtrics.SurveyEngine.addOnPageSubmit(function validateScalingFactorBounds() {
    var container = document.querySelector("#question-QID10") || document.querySelector("#QID10");
    if (!container) return true;

    var inputs = container.querySelectorAll("input.text-input, input[type='text'], input[type='number']");
    if (inputs.length < 3) return true;

    var v0 = inputs[0].value.trim();
    var v1 = inputs[1].value.trim();
    var v2 = inputs[2].value.trim();

    if (v0 === "" && v1 === "" && v2 === "") return true;

    var lower = parseFloat(v0);
    var upper = parseFloat(v1);
    var median = parseFloat(v2);

    if (v0 === "" || v1 === "" || v2 === "" || isNaN(lower) || isNaN(upper) || isNaN(median)) {
        alert("Please complete all three fields, or leave all blank to skip this question.");
        return false;
    }
    if (median <= lower) {
        alert("Your central estimate must be greater than your lower bound.");
        return false;
    }
    if (median >= upper) {
        alert("Your central estimate must be less than your upper bound.");
        return false;
    }
    return true;
});
```

## Q10 — Block 2: calculateScalingCheck

```javascript
Qualtrics.SurveyEngine.addOnPageSubmit(function calculateScalingCheck() {
    function roundBn(x) {
        if (isNaN(x)) return "—";
        var a = Math.abs(x);
        if (a < 1)   return (Math.round(x * 10) / 10).toFixed(1);
        if (a < 20)  return String(Math.round(x * 2) / 2);
        if (a < 200) return String(Math.round(x / 5) * 5);
        return String(Math.round(x / 25) * 25);
    }

    function roundPct(x) {
        if (isNaN(x)) return "—";
        if (Math.abs(x) < 1) return (Math.round(x * 10) / 10).toFixed(1);
        return String(Math.round(x));
    }

    var container = document.querySelector("#question-QID10") || document.querySelector("#QID10");
    if (!container) return true;

    var inputs = container.querySelectorAll("input.text-input, input[type='text'], input[type='number']");
    if (inputs.length < 3) return true;

    var v0 = inputs[0].value.trim();
    var v1 = inputs[1].value.trim();
    var v2 = inputs[2].value.trim();

    if (v0 === "" && v1 === "" && v2 === "") return true;

    var sLower  = parseFloat(v0);
    var sUpper  = parseFloat(v1);
    var sMedian = parseFloat(v2);

    if (isNaN(sLower) || isNaN(sUpper) || isNaN(sMedian)) return true;

    var dMedian = parseFloat(Qualtrics.SurveyEngine.getJSEmbeddedData("damages_median"));
    var share   = parseFloat(Qualtrics.SurveyEngine.getJSEmbeddedData("uk_share"));

    if (isNaN(share)) {
        var sharePct = parseFloat("${q://QID16/ChoiceTextEntryValue}");
        if (!isNaN(sharePct)) share = sharePct / 100;
    }

    var pakGdp = parseFloat(Qualtrics.SurveyEngine.getEmbeddedData("pakistan_gdp_bn")) || 408;
    var ukGdp  = parseFloat(Qualtrics.SurveyEngine.getEmbeddedData("uk_gdp_bn")) || 3786;
    var cvcGdp = parseFloat(Qualtrics.SurveyEngine.getEmbeddedData("cvc_gdp_bn")) || 4100;

    if (isNaN(dMedian) || isNaN(share)) return true;

    var gdpMult = cvcGdp / pakGdp;
    var cvfProxy = dMedian * gdpMult;

    var cvfL = cvfProxy * sLower;
    var cvfM = cvfProxy * sMedian;
    var cvfU = cvfProxy * sUpper;

    var ukL = cvfL * share;
    var ukM = cvfM * share;
    var ukU = cvfU * share;

    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_share_pct", (share * 100).toFixed(1));
    Qualtrics.SurveyEngine.setJSEmbeddedData("scaling_lower",  String(sLower));
    Qualtrics.SurveyEngine.setJSEmbeddedData("scaling_median", String(sMedian));
    Qualtrics.SurveyEngine.setJSEmbeddedData("scaling_upper",  String(sUpper));

    Qualtrics.SurveyEngine.setJSEmbeddedData("cvf_damages_proxy", roundBn(cvfProxy));
    Qualtrics.SurveyEngine.setJSEmbeddedData("damages_median_display", roundBn(dMedian));

    var pctDamagesM = parseFloat(Qualtrics.SurveyEngine.getJSEmbeddedData("pct_damages_gdp_median"));
    if (isNaN(pctDamagesM) && !isNaN(dMedian)) {
        pctDamagesM = (dMedian / pakGdp) * 100;
    }
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_damages_gdp_median_display", roundPct(pctDamagesM));

    Qualtrics.SurveyEngine.setJSEmbeddedData("cvf_flow_lower",  roundBn(cvfL));
    Qualtrics.SurveyEngine.setJSEmbeddedData("cvf_flow_median", roundBn(cvfM));
    Qualtrics.SurveyEngine.setJSEmbeddedData("cvf_flow_upper",  roundBn(cvfU));

    Qualtrics.SurveyEngine.setJSEmbeddedData("cvf_pct_gdp_lower",  roundPct((cvfL / cvcGdp) * 100));
    Qualtrics.SurveyEngine.setJSEmbeddedData("cvf_pct_gdp_median", roundPct((cvfM / cvcGdp) * 100));
    Qualtrics.SurveyEngine.setJSEmbeddedData("cvf_pct_gdp_upper",  roundPct((cvfU / cvcGdp) * 100));

    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_cvf_lower",  roundBn(ukL));
    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_cvf_median", roundBn(ukM));
    Qualtrics.SurveyEngine.setJSEmbeddedData("uk_cvf_upper",  roundBn(ukU));

    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_uk_cvf_lower",  roundPct((ukL / ukGdp) * 100));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_uk_cvf_median", roundPct((ukM / ukGdp) * 100));
    Qualtrics.SurveyEngine.setJSEmbeddedData("pct_uk_cvf_upper",  roundPct((ukU / ukGdp) * 100));

    return true;
});
```

---

# Q35 — Part 2 check your work

**Question text:** `Check your work` (minimal — body built by JS).  
**Hook:** `addOnReady`

```javascript
Qualtrics.SurveyEngine.addOnReady(function () {
    var host = this.getQuestionContainer();
    if (!host) return;

    var box = host.querySelector(".QuestionText")
        || host.querySelector('[class*="question-text"]')
        || host;

    function get(key) {
        var val = Qualtrics.SurveyEngine.getJSEmbeddedData(key);
        return (val !== null && val !== undefined && val !== "") ? val : "—";
    }

    function range(loKey, hiKey) {
        var lo = get(loKey);
        var hi = get(hiKey);
        if (lo === "—" || hi === "—") return "—";
        return lo + "–" + hi;
    }

    function withTilde(val) {
        return (val === "—") ? "—" : "~" + val;
    }

    box.innerHTML = [
        '<div style="font-size: 1.125rem; line-height: 1.6;">',

        '<p style="margin-bottom: 1.25em;">You estimated Pakistan\'s central financially assessable damages at about <strong>' + withTilde(get("damages_median_display")) + '</strong> billion USD (<strong>' + get("pct_damages_gdp_median_display") + '%</strong> of Pakistan GDP). Using that as a benchmark for Climate Vulnerable Forum (CVF) states collectively implies total damages on the order of <strong>' + withTilde(get("cvf_damages_proxy")) + '</strong> billion USD.</p>',

        '<p style="margin-bottom: 1.25em;">You selected a scaling factor of <strong>' + get("scaling_median") + '</strong>, with a range of <strong>' + get("scaling_lower") + '–' + get("scaling_upper") + '</strong>.</p>',

        '<p style="margin-bottom: 0.75em;">Over <strong>15 years</strong>, that would imply CVF-wide compensation or loss-and-damage transfers of roughly:</p>',
        '<ul style="margin-bottom: 1.25em;">',
        '<li>Lower: <strong>' + withTilde(get("cvf_flow_lower")) + '</strong> billion USD (<strong>' + withTilde(get("cvf_pct_gdp_lower")) + '%</strong> of CVF GDP)</li>',
        '<li>Central: <strong>' + withTilde(get("cvf_flow_median")) + '</strong> billion USD (<strong>' + withTilde(get("cvf_pct_gdp_median")) + '%</strong> of CVF GDP)</li>',
        '<li>Upper: <strong>' + withTilde(get("cvf_flow_upper")) + '</strong> billion USD (<strong>' + withTilde(get("cvf_pct_gdp_upper")) + '%</strong> of CVF GDP)</li>',
        '</ul>',

        '<p style="margin-bottom: 1.25em;">On the same UK responsibility share you gave earlier (<strong>' + get("uk_share_pct") + '%</strong>), that would imply UK transfers of roughly <strong>' + withTilde(get("pct_uk_cvf_median")) + '%</strong> of 2025 UK GDP (<strong>' + range("pct_uk_cvf_lower", "pct_uk_cvf_upper") + '%</strong>). This is <strong>' + withTilde(get("uk_cvf_median")) + '</strong> billion USD (<strong>' + range("uk_cvf_lower", "uk_cvf_upper") + '</strong> billion USD) over 15 years.</p>',

        '<p style="margin-bottom: 0.75em;"><strong>Does this outcome look plausible as a starting point for calibrating a climate scenario where inter-state compensation for loss and damage is a live issue?</strong></p>',

        '<p style="margin-bottom: 0.75em;"><em>Note that the check-your-work figures here are illustrative rounded estimates for calibration; precise values are retained in the dataset.</em></p>',

        '<p>If you want to change any answers, click <strong>Previous page</strong> now. Your updated answers will replace your earlier ones.</p>',

        '</div>'
    ].join("");
});
```

---

## Checklist before fieldwork

- [ ] All `__js_` fields in Survey Flow  
- [ ] GDP constants set  
- [ ] Q24 field order: lower / upper / median  
- [ ] Q10 field order: lower / upper / median  
- [ ] Calculation on **Q13** (not Q24)  
- [ ] Q15 HTML has all `ed_*` span ids  
- [ ] No debug `alert()` left in scripts  
- [ ] **Publish** after changes  
- [ ] Full preview: Q16 → Q24 → Q13 → Q15 → Q10 → Q35  

---

## Questions without JavaScript in this build

| Question | Role |
|----------|------|
| Q25 | Part 2 intro (text only) |
| Q1a, other Part 1 | No JS documented here (Q1a → Q24 pipe discussed separately) |
| Justification / 2b | Text or MC only |

---

*Generated from Cursor agent session on Qualtrics survey build.*
