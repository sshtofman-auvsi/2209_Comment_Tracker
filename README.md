# FAA-2026-4558 Comment Tracker

Live dashboard tracking public comments on the FAA Section 2209 NPRM — *Restrict the Operation of Unmanned Aircraft in Close Proximity to a Fixed Site Facility*.

## View the Dashboard

**[https://sshtofman-auvsi.github.io/2209_Comment_Tracker/](https://sshtofman-auvsi.github.io/2209_Comment_Tracker/)**

## What's in it

**Comments tab** — all 488 public comments from [regulations.gov](https://www.regulations.gov/document/FAA-2026-4558-0001/comment), searchable and filterable by type. PDF-attached comments have been extracted and are fully searchable.

**Analysis & Flags tab** — analytical synthesis for AUVSI's own comment filing:
- Position breakdown (all comments vs. genuine 2209 stakeholders, excluding the railroad-labor write-in campaign)
- Who filed and what themes dominate the record
- 116 hand-classified substantive stakeholder comments with position and key arguments
- 4 key takeaways and 8 draft-relevant flags with severity ratings

## Key finding

~63% of the docket (309 of 488 comments) is an organized railroad-labor write-in campaign by SMART-TD members protesting employer drone surveillance — an off-topic labor grievance, not engagement with the Section 2209 facility-designation framework. The dashboard leads with this context so the raw comment count is not misread as stakeholder consensus.

Among genuine 2209 stakeholders (179 comments): support-with-changes plurality (93), followed by support (50) and oppose (33).

## Data pipeline

Comments are fetched daily from the regulations.gov v4 API and committed automatically via GitHub Actions. The dashboard is a static file — no server required.

- **Docket:** FAA-2026-4558
- **Comment period:** closes July 6, 2026
- **Last updated:** see `docs/comments.json`
