# Product: Artgents

## What this is

Artgents is a multi-agent research and curation studio for physical fine art.
Given photos of a painting or sculpture (and whatever metadata is available),
it produces:

1. A visual/stylistic analysis of the work
2. A provenance and red-flag audit (ownership history, documented gaps,
   public theft/plunder records)
3. A heuristic market valuation range, backed by cited public comparable
   sales
4. Publication-ready exhibition copy and wall-label text for a gallery or
   auction house

## Problem

Galleries and auction houses spend hundreds of hours per piece on manual
work that is:
- Repetitive (comparable-sales research, provenance timeline assembly)
- High-stakes (missing a documented ownership gap has legal and
  reputational consequences)
- Time-boxed (exhibition copy has hard publication deadlines)

## Users

- Gallery curators preparing exhibition text
- Auction house researchers doing provenance due diligence
- Appraisers who want a first-pass heuristic valuation before deeper work

## Non-goals

- This is not a legal authority on stolen art status. It surfaces
  documented, publicly available red flags — it does not replace a formal
  Art Loss Register / Interpol check.
- This is not a definitive auction appraisal. Valuations are heuristic
  estimates derived from public comparable sales, clearly labeled as such.
- Not aiming for full attribution/authentication (i.e. "is this a genuine
  Picasso") — that's a much harder, higher-stakes claim than this project
  makes.

## Success criteria for the hackathon submission

- All four agents run against real, open, freely-accessible data sources
  (Wikidata, Met Museum API, Art Institute of Chicago API, Parallel Search)
- No mocked/fabricated data presented as live
- Every provenance or valuation claim in agent output carries a source URL
- A judge can run the deployed app and get a real result for a real,
  named artwork with no payment or credentials required