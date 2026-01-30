# Research Integrity and Responsible Practices

---

## Purpose

This document establishes mandatory research integrity standards for this project. All work must comply with these guidelines to prevent research misconduct and questionable research practices (QRPs).

---

## Core Principles

### 1. Research Misconduct vs. Questionable Research Practices

**Research Misconduct** (most serious):
- **Fabrication**: Making up data or results
- **Falsification**: Manipulating research data or results to misrepresent findings

**Questionable Research Practices (QRPs)**:
- Less severe but still harmful
- Often more common than misconduct
- Cumulative impact can exceed that of deliberate misconduct
- Include: selective reporting, inadequate record-keeping, ignoring data points, etc.

### 2. Spectrum of Irresponsible Behavior

Research integrity violations exist on a spectrum:
- **Minor**: Failing to cite a related publication
- **Moderate**: Selective referencing, inadequate documentation
- **Serious**: Ignoring inconvenient data points, not registering required trials
- **Severe**: Data fabrication, falsification, plagiarism

**All levels matter** - seemingly minor violations can have serious cumulative impacts.

---

## Specific Guidelines for This Project

### Data Integrity

**NEVER:**
- Fabricate data points or sentiment scores
- Alter ibkr-hmrc data or firm fundamentals to fit hypotheses
- Selectively exclude data points without justification and documentation
- Fill data gaps with assumptions without explicit disclosure
- Manipulate results to achieve statistical significance

**ALWAYS:**
- Document ALL data processing steps
- Keep complete records of data transformations
- Preserve raw data in original form
- Document reasons for any data exclusions with full transparency
- Report negative results and null findings
- Maintain audit trails for all analysis runs

### Analysis Integrity

**NEVER:**
- Run multiple analyses and only report the "best" results (p-hacking)
- Change hypotheses after seeing results (HARKing - Hypothesizing After Results are Known)
- Ignore data that contradicts your theory
- Stop data collection when results look "good enough"
- Use expert judgment to fill data gaps without clear disclosure

**ALWAYS:**
- Pre-register analysis plans where possible
- Document all analysis decisions and their rationale in `docs/discussions/`
- Report all analyses conducted, not just successful ones
- Be transparent about exploratory vs. confirmatory analyses
- Save all analysis outputs with timestamps in `analysis/` folders
- Document any deviations from planned analyses

### AI Usage (Claude, ChatGPT, etc.)

**NEVER:**
- Use AI to generate fake data
- Let AI write sections without verification and attribution
- Use AI-generated content without disclosure
- Rely on AI for critical methodological decisions without expert consultation
- Use AI to fabricate references or citations

**ALWAYS:**
- Disclose all AI usage
- Verify all AI-generated content against original sources
- Document specific AI tools and versions used
- Use AI responsibly for: coding assistance, literature search, draft editing, idea exploration
- Keep records of significant AI interactions in `docs/discussions/ai-usage-log.md`
- Maintain human oversight and critical judgment
- Consult field experts before integrating AI-generated methodological suggestions

### Citation and Attribution

**NEVER:**
- Use others' ideas without attribution
- Copy code without proper licensing and credit
- Fail to cite sources for methodological approaches
- Present collaborative work as solely your own

**ALWAYS:**
- Cite all sources of ideas, methods, data, and code
- Maintain a comprehensive bibliography
- Give proper credit to collaborators and advisors
- Document code sources and licenses
- Attribute theoretical frameworks to original authors

### Record Keeping

**NEVER:**
- Rely on memory for important decisions
- Delete original data or analysis files
- Work without documentation

**ALWAYS:**
- Document research decisions in real-time in `docs/discussions/`
- Maintain version control for all code and analysis
- Keep lab notebooks/research logs with timestamps
- Preserve all iterations of analysis outputs
- Document methodological changes and rationale

### Statistical and Methodological Rigor

**NEVER:**
- Selectively report statistics
- Change methodology mid-project without documentation and justification
- Ignore violations of statistical assumptions
- Cherry-pick time periods or firms to improve results

**ALWAYS:**
- Report full statistical results (not just p-values)
- Document sensitivity analyses
- Test robustness of findings
- Report effect sizes and confidence intervals
- Disclose all model specifications tested
- Be transparent about data-driven decisions
- Document all methodological limitations

---

## Preventing Common QRPs

### Before Starting Analysis

**Self-Check Questions:**
1. Is my research question relevant and original?
2. Has similar research been done before?
3. Is this the best use of time and resources?
4. Do I have a clear, documented research plan?

### During Data Collection

**Self-Check Questions:**
1. Am I collecting data systematically?
2. Am I documenting all collection procedures?
3. Am I preserving raw data?
4. Have I encountered any issues that need documentation?

### During Analysis

**Self-Check Questions:**
1. Am I following my pre-specified plan?
2. Am I documenting deviations and their rationale?
3. Am I keeping records of all analyses run?
4. Am I considering alternative explanations?

### During Writing

**Self-Check Questions:**
1. Have I cited all sources properly?
2. Am I reporting all relevant results, including null findings?
3. Am I transparent about limitations?
4. Have I disclosed all conflicts of interest?
5. Have I disclosed AI usage?

---

## Red Flags and Warning Signs

**Stop and reconsider if you find yourself:**
- Thinking "I'll just adjust this one data point..."
- Wanting to exclude "outliers" without statistical justification
- Running "just one more analysis" to get the results you want
- Thinking "this is close enough to what I wanted"
- Not documenting a decision "because it's obvious"
- Using your own judgment to fill data gaps without disclosure
- Hiding negative or inconvenient results
- Changing hypotheses after seeing results

**If you experience any of these, STOP and:**
1. Document what you were about to do
2. Discuss with supervisor/advisor
3. Review this document
4. Document the proper approach in `docs/discussions/`

---

## Impact of Irresponsible Practices

### Why This Matters

**Professional Impact:**
- Career damage and loss of reputation
- Retracted publications
- Loss of funding
- Potential job loss

**Research Community Impact:**
- Wasted resources on following false leads
- Erosion of public trust in research
- Delayed scientific progress
- Harm to participants/society if false findings are applied

**Personal Impact:**
- Stress and anxiety
- Damaged relationships with colleagues
- Legal consequences in severe cases

**Remember:** Even "small" QRPs accumulate and undermine the entire research enterprise.

---

## Handling Questionable Situations

### If You're Unsure About a Practice

2. **Consult this document** for guidance
3. **Discuss with user** before proceeding
4. **Err on the side of transparency** - when in doubt, disclose
5. **Document the resolution** and rationale

### If You Observe Irresponsible Practices

**In your own work:**
- Stop immediately
- Document what happened
- Consult user
- Correct the issue
- Document the correction

**In others' work:**
- Consider whether it rises to the level requiring reporting
- Consult institutional guidelines (UKRIO)
- Seek advice from research office if needed
- Remember: you have an obligation to report serious misconduct

---

## Documentation Requirements

### Required Documentation

All research activities must be documented in appropriate locations:

1. **Data Processing**: Document in code comments and `README.md`
2. **Methodological Decisions**: Document in `docs/discussions/`
3. **Analysis Rationale**: Save with results in `analysis/` folders
4. **Deviations from Plan**: Document in `docs/discussions/methodology-changes.md`
5. **AI Usage**: Log in `docs/discussions/ai-usage-log.md`
6. **Ethical Questions**: Document in `docs/discussions/ethics-questions.md`

### Documentation Standards

- **Real-time**: Document decisions when made, not retrospectively
- **Complete**: Include context, rationale, alternatives considered
- **Honest**: Acknowledge uncertainties and limitations
- **Transparent**: Write as if a reviewer will read it (they might)

---

## Pre-Submission Checklist

Before submitting any work (dissertation, paper, etc.), verify:

### Data Integrity
- [ ] All data sources properly cited
- [ ] Raw data preserved and accessible
- [ ] Data processing fully documented
- [ ] No fabricated or falsified data
- [ ] All data exclusions justified and documented
- [ ] No selective reporting of data

### Analysis Integrity
- [ ] All analyses documented
- [ ] Negative results reported
- [ ] Alternative explanations considered
- [ ] Statistical assumptions verified
- [ ] Sensitivity analyses conducted
- [ ] No p-hacking or HARKing

### Transparency
- [ ] All methods fully described
- [ ] All limitations acknowledged
- [ ] All conflicts of interest disclosed
- [ ] AI usage fully disclosed
- [ ] Collaborator contributions acknowledged

### Attribution
- [ ] All sources properly cited
- [ ] No plagiarism
- [ ] Code sources and licenses documented
- [ ] Theoretical frameworks properly attributed

### Documentation
- [ ] Research decisions documented in `docs/discussions/`
- [ ] Analysis outputs saved with timestamps
- [ ] Methodological changes documented and justified
- [ ] Complete audit trail maintained

---

## Enforcement

### This is MANDATORY

- These guidelines are **not optional**
- They apply to **all project work**
- They supersede desires for "better results"
- **No exceptions** without documented supervisor approval

### If Claude (AI) Observes Violations

When working with Claude Code, if practices violate these guidelines, Claude will:

1. **Stop immediately** and refuse to proceed
2. **Point to this document** and the specific violation
3. **Suggest the proper approach**
4. **Require documentation** before proceeding

### Accountability

- **You** are responsible for maintaining these standards
- **Supervisors** are responsible for oversight
- **The institution** is responsible for investigating allegations
- **The research community** depends on your integrity

---

## Resources

### External
- UK Government Whistleblowing Guidelines: https://www.gov.uk/whistleblowing
- UKRIO Advice: https://ukrio.org/our-work/get-advice-from-ukrio/
- Health and Care Professions Council Whistleblowing Policy: https://www.hcpc-uk.org/resources/policy/whistleblowing-policy/

### Project-Specific
- `docs/discussions/` - Ongoing research decisions
- `analysis/` folders - Complete analysis records
- `README.md` - Technical documentation
- `docs/project_background/` - Methodological foundation

---

## Updates to This Document

This is a **living document**. Update it when:
- New ethical issues arise
- Guidelines change
- Best practices evolve
- Project needs expand

**Document all changes** with date, reason, and impact.

---

## Acknowledgment

By working on this project, you acknowledge:
1. You have read and understood these guidelines
2. You will comply with these standards
3. You will report violations
4. You understand the consequences of irresponsible practices
5. You are committed to research integrity

**Research integrity is not negotiable. It is the foundation of trustworthy science.**
