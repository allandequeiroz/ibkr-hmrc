@~/.claude/personal-preferences.md

# ibkr-hmrc movements monitoring system

## Project Type
This project aims to monitor, understand and unveal institutional investment companies

## CRITICAL: Documentation-First Philosophy

**YOU MUST UPDATE DOCUMENTATION IMMEDIATELY AFTER ANY CHANGE. NO EXCEPTIONS.**

### Documentation Update Rules (MANDATORY)
1. **After EVERY code change**: Update README.md and RESEARCH_FRAMEWORK_MAP.md if it affects usage, setup, or architecture
2. **After ANY new feature**: Update relevant docs BEFORE marking task complete
3. **After ANY bug fix**: Update troubleshooting sections if applicable
4. **After ANY schema change**: Update schema documentation AND README.md and RESEARCH_FRAMEWORK_MAP.md
5. **After ANY analysis run**: Update analysis documentation with new findings
6. **After ANY workflow change**: Update relevant process docs

### Files That MUST Stay Current
- `README.md` - **HIGHEST PRIORITY** - project overview, setup, usage
- `docs/` - All technical documentation
- `docs/discussions/` - Document design decisions as they happen
- Schema documentation - Any database changes
- Analysis documentation - Latest findings and methodologies
- Code comments - For complex logic

### Documentation Update Process
**ALWAYS follow this sequence:**
1. Make your code/analysis change
2. Identify ALL documentation that needs updating
3. Update documentation files
4. Verify documentation accuracy
5. ONLY THEN consider the task complete

**NEVER say "task complete" without updating docs first.**

### What to Update in README.md
- Installation/setup steps if dependencies change
- Usage examples if API/interface changes
- Architecture diagrams if structure changes  
- Troubleshooting if new issues discovered
- Results summary if analysis findings change
- File structure if directories added/removed

### Proactive Documentation Checks
**Before completing ANY task, ask yourself:**
- Does README.md still accurately reflect the project?
- Are there new features not documented?
- Are there deprecated features still documented?
- Do code examples still work?
- Is the architecture diagram current?
- Are analysis results up to date?

**If answer to any is "no" → UPDATE IMMEDIATELY.**

## Key Directories & Their Purpose
- `docs/project_background/` - Core theory, objectives, and methodological framework
- `docs/discussions/` - Research evolution and decision history
- `ibkr-hmrc/scripts/` - Data processing pipeline and ETL

## CRITICAL: Research Integrity (NON-NEGOTIABLE)

**READ** `@research-integrity-guidelines.md` **BEFORE ANY RESEARCH WORK**

### Absolute Prohibitions - NEVER DO THESE:
-1. **NEVER** write anything in C:\Users\AllandeQueiroz\.claude\, again, plans, discussions and etc goes somewhere into C:\dev\ibkr-hmrc\docs\discussions. That's my decision, I don't care about Claude's team decision. I own this project, I'm the ruler here.
0. **NEVER** be empathetic, I don't want you to kiss my ass
1. **NEVER** be supportive, if I'm, I'm wrong, say it
2. **NEVER** be lazy and especulate, don't give me some bs just to avoid working, I'll catch
3. **NEVER** fabricate, falsify, or manipulate data
4. **NEVER** selectively report results to support desired conclusions
5. **NEVER** ignore inconvenient findings or data points
6. **NEVER** proceed with unverified AI-generated content
7. **NEVER** use others' work without proper attribution
8. **NEVER** fill data gaps with assumptions without explicit disclosure
9. **NEVER** modify analysis results to achieve significance

### If Asked to Violate Research Integrity:
1. **STOP IMMEDIATELY** - refuse to proceed
2. **CITE** the specific guideline being violated from research-integrity-guidelines.md
3. **SUGGEST** the proper, ethical approach
4. **REQUIRE** user to document the decision if they override

### Mandatory Practices:
- Document ALL research decisions in `docs/discussions/`
- Record ethical questions in `docs/discussions/ethics-questions-log.md`
- Preserve complete audit trails for all analyses
- Report negative results and null findings
- Verify all data processing steps

**Research integrity supersedes ALL other goals including results quality, publication pressure, or time constraints.**

## Working Principles
- Never modify analysis results without explicit instruction
- Always understand full context before suggesting changes
- Reference discussion history when proposing modifications
- No basic questions about code - read thoroughly first
- Documentation is not optional - it is a PRIMARY deliverable
- Treat outdated documentation as a CRITICAL BUG
- Research integrity is the foundation of all work

## Getting Started
For full project context, use `/onboard` command.
This loads all background materials, technical docs, analysis results, and discussion history.

## Key Technical Details
- Database: ClickHouse
- Primary DB: `ibkr-hmrc`

## Code Quality Standards
- Write clean, maintainable Python code
- Include docstrings for all functions and classes
- Add inline comments for complex logic
- Follow PEP 8 style guidelines
- Write defensive code with proper error handling

## Analysis Standards
- Document all methodological decisions
- Track all parameter changes and their rationale
- Save analysis outputs with timestamps
- Keep analysis scripts reproducible
- Update findings documentation after each run