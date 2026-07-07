"""
Analyze FAA-2026-4558 comments: classify position/category/themes, detect the
railroad-labor write-in campaign, compute aggregates, and emit a curated
synthesis of trends and flags for AUVSI's own comment draft.

Outputs docs/analysis.js  ->  const ANALYSIS_DATA = {...}

Design:
- Substantive 2209 stakeholder comments are hand-verified in CURATED (sourced
  from a one-time multi-agent read of every comment). These are authoritative.
- The bulk railroad-labor campaign is detected programmatically from text, so
  the numbers stay correct as new comments flow in via the daily pipeline.
- The curated TAKEAWAYS / FLAGS are the analytical layer for the draft.

Usage:  python scripts/analyze_comments.py
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DOCS = Path(__file__).parent.parent / "docs"
COMMENTS = DOCS / "comments.json"
OUT = DOCS / "analysis.js"

# ---------------------------------------------------------------------------
# Curated classifications for substantive (non-campaign) 2209 stakeholders.
# id -> (category, position, [arguments])  ; verified from full-text read.
# ---------------------------------------------------------------------------
CURATED = {
    # --- Critical infrastructure / utility owners (mostly SUPPORT, want more) ---
    "FAA-2026-4558-0027": ("critical_infrastructure_owner", "support_with_changes", ["Explicitly include data centers as eligible", "Recognize cross-sector cascading impacts", "Judge by operational criticality not classification"]),
    "FAA-2026-4558-0043": ("critical_infrastructure_owner", "support", ["QTS data centers as critical infrastructure", "Align with DHS/CISA NIPP risk framework", "Supports two-tier petition model, 400ft ceiling"]),
    "FAA-2026-4558-0052": ("critical_infrastructure_owner", "support", ["Petition process for refineries/chemical/maritime", "Boundaries based on operational risk/footprint", "Permanent and temporary options"]),
    "FAA-2026-4558-0224": ("critical_infrastructure_owner", "support_with_changes", ["Expedite eligibility for MTSA-regulated ports", "Recognize port authorities as applicants", "Allow boundaries beyond property lines"]),
    "FAA-2026-4558-0252": ("critical_infrastructure_owner", "support", ["UAFRs over CN Great Lakes marine terminals", "Critical steelmaking infrastructure", "Enthusiast drones create risk"]),
    "FAA-2026-4558-0323": ("critical_infrastructure_owner", "support_with_changes", ["Protect CI from drone threats", "Keep UAFR requests confidential and FOIA-exempt"]),
    "FAA-2026-4558-0031": ("utility_water_energy", "support", ["Closes water/wastewater security gap"]),
    "FAA-2026-4558-0050": ("utility_water_energy", "support", ["Water utility protecting 1M people", "Sites attract drone pilots, counter-drone hard", "Concern over jailbroken drones, enforcement speed"]),
    "FAA-2026-4558-0051": ("utility_water_energy", "support_with_changes", ["Good first step but insufficient", "CI needs counter-drone technology"]),
    "FAA-2026-4558-0078": ("utility_water_energy", "support", ["Drone crashed onto Jones Island water facility", "Preemption confusion over who protects assets", "Backs state and federal protection"]),
    "FAA-2026-4558-0082": ("utility_water_energy", "support_with_changes", ["Include water/wastewater as eligible CI", "Broad interpretation of covered water infrastructure", "Efficient application process"]),
    "FAA-2026-4558-0186": ("utility_water_energy", "support", ["Gas midstream/LNG critical infrastructure", "No-fly zones at LNG sites enhance security"]),
    "FAA-2026-4558-0217": ("utility_water_energy", "support_with_changes", ["Support 400ft restriction over water facilities", "Remote ID exception prudent", "Add counter-drone capture/disable and jamming authority"]),
    "FAA-2026-4558-0080": ("public_safety", "support_with_changes", ["Hospitals need restriction for patient privacy", "Protect medical helicopter landing zones", "Immediate enforcement for life-critical care"]),
    "FAA-2026-4558-0240": ("public_safety", "support_with_changes", ["Recognize hospitals/heliports as CI", "Near-miss UAV within 100ft of HEMS aircraft", "Active geofencing beyond passive Remote ID"]),
    "FAA-2026-4558-0021": ("public_safety", "support_with_changes", ["Clear emergency exemption for public-safety UAS", "Smallest practicable boundaries", "Remote ID alone insufficient to validate operators"]),
    "FAA-2026-4558-0025": ("public_safety", "support_with_changes", ["Permit public safety Part 107 operations", "Preserve notice-not-permission", "Harmonize with SGI process"]),
    "FAA-2026-4558-0053": ("public_safety", "support", ["Limit drones over schools", "Nefarious drones drop items onto campuses"]),
    "FAA-2026-4558-0400": ("public_safety", "support_with_changes", ["Public safety Part 107 notice-based within UAFRs", "Volunteer fire treated as public safety", "Clarify interaction with state/local laws"]),
    "FAA-2026-4558-0197": ("other", "support", ["Arena: 500,000 people across 85 events/yr", "Drones a hazard and disruption to events"]),

    # --- Commercial drone operators / surveyors (SUPPORT-WITH-CHANGES: access) ---
    "FAA-2026-4558-0182": ("drone_company", "support_with_changes", ["Preserve fast access for surveying/mapping", "Transition standard misfits non-transitory mapping", "Adopt LAANC-style instant notice", "Add contractor pathway for asset-owner work"]),
    "FAA-2026-4558-0013": ("drone_company", "support_with_changes", ["Dense NJ region risks overlapping patchwork", "Tightly define close proximity/boundaries", "LAANC-like authorization", "Enforce demonstrated need"]),
    "FAA-2026-4558-0038": ("drone_company", "support_with_changes", ["Per-flight notice unworkable for contracted inspections", "Create Authorized Contracted Operator standing authorization", "Economic impact underestimated"]),
    "FAA-2026-4558-0042": ("drone_company", "support_with_changes", ["Concern over broad lateral limits along rail main lines", "Strictly define fixed-site, limit to high-value assets", "Safe transit provisions, tiered implementation"]),
    "FAA-2026-4558-0414": ("drone_company", "support_with_changes", ["Minimally burdensome on operators", "High bar: site-specific credible threat evidence", "Automate approvals like LAANC, public boundaries"]),
    "FAA-2026-4558-0011": ("individual_part107_operator", "support_with_changes", ["UAS-only restriction discriminatory vs manned", "Safeguards against overreach, standardized access", "Restrictions must appear in mapping tools"]),
    "FAA-2026-4558-0214": ("individual_part107_operator", "support_with_changes", ["Preserve fast Part 107 survey/mapping access", "LAANC-style centralized fast approval", "Contractor pathway, deemed-approval deadlines"]),
    "FAA-2026-4558-0266": ("individual_part107_operator", "support_with_changes", ["Supports Part 74/2209", "Eight refinements to balance public transit", "Credibility pathway for vetted operators"]),
    "FAA-2026-4558-0221": ("individual_part107_operator", "support_with_changes", ["Supports Part 74 framework", "Notice impossible during active SAR", "Credibility pathway for vetted public-safety operators"]),
    "FAA-2026-4558-0351": ("individual_part107_operator", "support_with_changes", ["Strengthen transit carve-out", "Machine-readable real-time UAFR data", "Evidence-based minimum dimensions", "Prevent anti-competitive petition abuse"]),
    "FAA-2026-4558-0353": ("individual_part107_operator", "support_with_changes", ["LAANC-style notify-and-fly", "Limit boundaries to property footprint", "Absolute federal preemption over CI airspace", "Keep cUAS authority separate"]),
    "FAA-2026-4558-0356": ("individual_part107_operator", "support_with_changes", ["Closing 2209 gap is overdue", "LAANC for Part 107 access to Standard UAFRs", "Strong federal preemption", "Documented-need filter on petitions"]),
    "FAA-2026-4558-0370": ("individual_part107_operator", "support_with_changes", ["Rule overly broad, patchwork risk", "Strict criteria, narrowly tailored zones", "Simple LAANC-like authorization"]),
    "FAA-2026-4558-0341": ("individual_part107_operator", "support_with_changes", ["Transit notification unworkable nearby", "Add CI facilities to LAANC", "Exempt sub-250g recreational", "Not all CI carries equal risk"]),
    "FAA-2026-4558-0144": ("individual_part107_operator", "support_with_changes", ["Licensed pilot supports restrictions", "Include rail; restrict routine crew monitoring", "Allow inspection/emergency uses"]),
    "FAA-2026-4558-0026": ("individual_part107_operator", "support_with_changes", ["Concern over economic/operational impacts", "Increased compliance and coordination burdens"]),
    "FAA-2026-4558-0017": ("individual_part107_operator", "support_with_changes", ["Restrict ALL aircraft not just drones for enforceability", "Include facility's own UAV use to deter frivolous requests"]),
    "FAA-2026-4558-0033": ("individual_part107_operator", "support", ["Supports for safety near refineries/prisons", "Clear boundaries ease compliance", "Must appear on LAANC/maps immediately"]),

    # --- C-UAS detection vendors (SWC: recognize passive detection) ---
    "FAA-2026-4558-0285": ("cuas_vendor", "support_with_changes", ["Remote ID alone can't detect non-cooperative drones", "Recognize passive radar as approved methodology", "Define data integration standards"]),
    "FAA-2026-4558-0387": ("cuas_vendor", "support_with_changes", ["Recognize lawful passive receive-only detection", "Remote ID reception a floor not ceiling", "Technology-neutral standards"]),
    "FAA-2026-4558-0040": ("cuas_vendor", "support_with_changes", ["Enforcement automated via approved platform", "Offers to demo solution"]),

    # --- Media / photography (OPPOSE or SWC) ---
    "FAA-2026-4558-0022": ("media_photography", "support_with_changes", ["Shortest-practicable-time bars newsgathering", "Extend breaking-news flexibility to journalism", "Whitelist for vetted Part 107", "Simultaneous publication in pilot feeds"]),
    "FAA-2026-4558-0030": ("media_photography", "support_with_changes", ["Facility-requested shoots could be blocked", "Fast-track waiver when facility sponsors", "LAANC-like portal for credentialed operators"]),
    "FAA-2026-4558-0261": ("media_photography", "oppose", ["Nationwide patchwork of permanent exclusion zones", "Property ownership doesn't confer airspace ownership", "Require documented evidence not speculative risk"]),
    "FAA-2026-4558-0357": ("media_photography", "oppose", ["Urban operations made impractical", "CI woven through urban landscape blocks airspace", "Use LAANC-style system instead"]),
    "FAA-2026-4558-0019": ("media_photography", "oppose", ["First Amendment footage-gathering rights", "Destroys government transparency"]),
    "FAA-2026-4558-0049": ("media_photography", "oppose", ["Kills legal/safe railroad drone photography", "Railroads themselves use drones for media"]),
    "FAA-2026-4558-0076": ("media_photography", "oppose", ["Kills railroad drone photography hobby/business", "Fragmented airspace hard to navigate"]),

    # --- Drone companies opposing / withdraw ---
    "FAA-2026-4558-0039": ("drone_company", "oppose", ["Patchwork of private exclusion zones", "Notice must be informational not permission", "Integrate into LAANC; keep inside property lines"]),
    "FAA-2026-4558-0149": ("drone_company", "oppose", ["Withdraw; pursue narrower security approach", "Real threat is insecure foreign-origin drones", "Limit to DOD/DOE unless Congress authorizes"]),
    "FAA-2026-4558-0255": ("drone_company", "oppose", ["Connectivity logic could lock down public skies", "Remote ID makes blanket bans redundant", "Use micro-airspaces not multi-mile zones"]),
    "FAA-2026-4558-0364": ("drone_company", "oppose", ["Drones already heavily regulated", "Hurts legitimate businesses", "Bad actors won't follow new rule"]),

    # --- Trade associations ---
    "FAA-2026-4558-0343": ("trade_association", "support_with_changes", ["Support rule for working waterfront", "Requests refinements to UAFR framework"]),
    "FAA-2026-4558-0350": ("trade_association", "support_with_changes", ["LAANC-style notify-and-fly for all FAA-authorized ops (Part 107, 44809, 135, 137)", "Require documented UAS incursions before Standard UAFR granted; mere concern insufficient", "Boundaries limited to fence line; buffer zones only if standardized nationwide", "Explicitly prohibit private UAS mitigation/interdiction (SAFER SKIES Act)", "Avoid transit-only restriction — allow inspect/map/photograph over facility", "Strong federal preemption; proposes specific § 74.240 CFR language"]),

    # --- Government agencies ---
    "FAA-2026-4558-0194": ("government_agency", "support", ["Restrict over wastewater/SICSO facilities", "Reconnaissance and ICS threat", "Safety hazard to field personnel"]),
    "FAA-2026-4558-0253": ("government_agency", "support_with_changes", ["UAFRs could block recurring inspection flights", "Streamlined process for statewide DOTs", "Publish UAFR data machine-readable"]),
    "FAA-2026-4558-0352": ("government_agency", "support_with_changes", ["Recognize municipal water/wastewater", "Exempt municipal-operated drones", "Streamline application for local government"]),
    "FAA-2026-4558-0403": ("government_agency", "support_with_changes", ["7460-style state stakeholder review of UAFR applications before FAA decision", "States should be able to apply for expedited UAFRs during regional emergencies (hurricanes)", "Integrate UAFR data with state UAS Flight Information Exchanges (VA, PA, WV, OH, OK FIX's)", "Tiered boundaries: property line sufficient for venues but not defense/CI facilities (e.g., Huntington Ingalls Shipyard espionage risk)", "UAFR applications shared with state agencies for NEPA compliance", "General aviation airport traffic patterns and approach/departure corridors should be eligible permanent UAFR areas"]),
    "FAA-2026-4558-0417": ("government_agency", "unclear", ["NY Attorney General — requests 30-day comment period extension"]),
    "FAA-2026-4558-0419": ("government_agency", "support_with_changes", ["9 bridges and 6 tunnels qualify", "Holistic network approach to infrastructure", "Preserve state authority over ROW", "Avoid diminishing state DOT role"]),

    # --- Academic / test sites ---
    "FAA-2026-4558-0047": ("academic", "support_with_changes", ["Drones standard in research/hospitals", "LAANC to notify local AHJs", "Optional registration for alerts"]),
    "FAA-2026-4558-0048": ("academic", "support", ["UAFR for BSL-4 biodefense CI", "Protect infectious-disease research"]),
    "FAA-2026-4558-0371": ("academic", "support_with_changes", ["Define good cause objectively", "3-year revalidation review", "Sustained-operations approval process"]),

    # --- Hobbyists / individuals opposing on overreach grounds ---
    "FAA-2026-4558-0010": ("individual_other", "oppose", ["Drone-only restriction unjustified vs manned aircraft", "Require documented site-specific UAS threat", "FAA-run notification not private permission"]),
    "FAA-2026-4558-0014": ("individual_other", "oppose", ["Fragments navigable airspace", "Fear of mission creep onto manned aircraft", "Narrow to demonstrated UAS-specific threats"]),
    "FAA-2026-4558-0034": ("individual_other", "oppose", ["Cedes FAA authority to private organizations", "Dangerous precedent neutering agency authority", "Only FAA/military/nuclear should request"]),
    "FAA-2026-4558-0037": ("individual_other", "oppose", ["Corporations shouldn't own blocks of public airspace", "Public airspace should remain public"]),
    "FAA-2026-4558-0035": ("individual_hobbyist", "oppose", ["125,000 sites privatizes airspace into Swiss cheese", "Remote ID logging weaponized for surveillance", "Carve-out for recreational VLOS"]),
    "FAA-2026-4558-0029": ("individual_hobbyist", "oppose", ["Patchwork of navigable airspace", "Existing trespass laws cover misuse", "Banning the tool not the criminal act"]),
    "FAA-2026-4558-0041": ("individual_hobbyist", "oppose", ["Only affects law-abiding hobbyists", "Corporate airspace ownership absurd", "Wasteful administrative costs"]),
    "FAA-2026-4558-0046": ("individual_hobbyist", "oppose", ["Slippery slope, constitutional freedom", "LAANC already handles notification", "Focus on criminals not DJI mini hobbyists"]),
    "FAA-2026-4558-0340": ("individual_hobbyist", "oppose", ["Current restrictions sufficient", "More rules ruin hobby aerial photography", "Punish reckless operators individually"]),
    "FAA-2026-4558-0058": ("individual_part107_operator", "oppose", ["Railroads could blanket-ban hobbyist flights", "Tracks parallel public roads, overbroad", "Urges FAA reject and restructure"]),
    "FAA-2026-4558-0210": ("individual_other", "oppose", ["Frames rule as DJI-lobby-driven", "Alleges improper DJI influence over airspace", "Urges FARA investigation of rulemaking"]),
    "FAA-2026-4558-0036": ("individual_other", "support_with_changes", ["Outright ban over non-military sites draconian", "Prohibit below 100ft only, allow 100-400ft", "Security-photography claim dubious vs GA aircraft"]),
    "FAA-2026-4558-0073": ("individual_other", "support_with_changes", ["Amusement parks shouldn't count as CI", "Parks can use TFRs", "Nuclear plants legitimate, water parks not"]),
    "FAA-2026-4558-0016": ("individual_hobbyist", "support", ["Balanced risk-based restrictions appropriate", "Narrowly tailored to high-risk sites"]),
    "FAA-2026-4558-0152": ("individual_other", "support_with_changes", ["125,000 facilities cumulative airspace impact", "Sector criteria undefined, finalize first", "Integrate UAFRs into LAANC"]),
    "FAA-2026-4558-0416": ("individual_other", "support_with_changes", ["Drone threat to infrastructure credible", "Include high-density venues like stadiums", "Narrow buffers, LAANC fast-track", "Notes rail-labor comments are off-scope surveillance dispute"]),

    # --- Labor union (official filings, on-topic-ish) ---
    "FAA-2026-4558-0106": ("labor_union", "support", ["Opposes drones in transportation infrastructure", "Drones easily weaponized by bad actors", "Workers can't distinguish authorized from hostile"]),
    "FAA-2026-4558-0120": ("labor_union", "support_with_changes", ["Rule ignores carrier's own drones", "Can't tell company drone from hostile", "FAA should consult SMART-TD and BLET"]),

    # --- Substantive individuals not in the campaign (verified) ---
    "FAA-2026-4558-0024": ("individual_other", "oppose", ["What is illegal today that isn't already covered?", "Existing laws cover trespass and misuse", "Overreach without proving a gap"]),
    "FAA-2026-4558-0018": ("individual_other", "support_with_changes", ["Guard against UAFR expansion fragmenting airspace", "Clearer eligibility and transparency", "Model cumulative impact on BVLOS"]),
    "FAA-2026-4558-0219": ("individual_other", "support", ["UAS industry has grown significantly", "Supports clear boundaries and accountability"]),
    "FAA-2026-4558-0229": ("individual_other", "support_with_changes", ["Supports facility-bound perimeter", "Restriction should apply to all aircraft not just UAS"]),
    "FAA-2026-4558-0044": ("individual_other", "support", ["Excellent long-awaited rulemaking", "Clarify FOIA protection for vulnerability info", "Close public-way loophole"]),
    "FAA-2026-4558-0020": ("individual_other", "support", ["KY infrastructure vulnerable", "Fund law enforcement detection via grants"]),
    "FAA-2026-4558-0045": ("individual_other", "support", ["Long overdue; protect nuclear plants and CI"]),
    "FAA-2026-4558-0071": ("individual_other", "support_with_changes", ["Exemption for SAR and disaster relief", "Staffed phone number not AI", "Limit to Part 107 holders"]),
    "FAA-2026-4558-0192": ("individual_other", "support_with_changes", ["Make fire, ambulance, law enforcement stations eligible"]),
    "FAA-2026-4558-0189": ("individual_other", "support_with_changes", ["Extend to temporary water/wastewater repair sites"]),
    "FAA-2026-4558-0195": ("individual_other", "oppose", ["Opposes restriction", "What defines close proximity or important fixed site?"]),
    "FAA-2026-4558-0153": ("individual_other", "support_with_changes", ["Aviation student", "125,000 facilities cumulative airspace impact", "Integrate UAFRs into LAANC"]),
    "FAA-2026-4558-0222": ("individual_other", "support_with_changes", ["Supports UAFR process", "Restrictions must be easy to find", "Facility ops without undue delay"]),
    "FAA-2026-4558-0012": ("individual_other", "unclear", ["Asks how rule interacts with existing SSI sites"]),
    "FAA-2026-4558-0298": ("individual_other", "unclear", ["Asks whether drones restricted over amusement parks"]),
    "FAA-2026-4558-0218": ("academic", "support_with_changes", ["Commends FAA for 2209 NPRM as CI protection milestone", "§ 74.54 eligibility language should reference all criteria, not only subsection (c)", "§ 74.255 access notification: include Remote ID serial number; needs streamlined process", "UAFR boundaries should be proportional and evidence-based", "Preserve scalable commercial drone access alongside CI protection"]),

    # --- Batch reviewed 2026-07-06: previously unreviewed org filings ---
    "FAA-2026-4558-0422": ("drone_company", "support_with_changes", ["UAFR needs a coordination layer with local law enforcement/emergency management", "Require UAFR boundary data published machine-readable on the effective date", "Operators should never discover a UAFR through violation"]),
    "FAA-2026-4558-0420": ("drone_company", "support_with_changes", ["Rule creates restrictions with no corresponding authorization pathway", "Mandate a LAANC-style fast-track authorization for facility-invited commercial operators", "Pre-register authorized operators by Remote ID with logged records"]),
    "FAA-2026-4558-0421": ("drone_company", "support_with_changes", ["Remote ID reception alone can't catch malicious non-cooperative operators", "Explicitly recognize passive, non-cooperative detection under § 74.56", "Clarify passive detection doesn't constitute unlawful 'interference'"]),
    "FAA-2026-4558-0423": ("critical_infrastructure_owner", "support_with_changes", ["Supports UAFR construct as deterrence and situational-awareness tool", "Framework should stay practical, risk-informed, operationally implementable", "UAFRs are a first step; scalable lawful counter-UAS capability still needed"]),
    "FAA-2026-4558-0426": ("trade_association", "oppose", ["FAA-recognized CBO representing 1.5M recreational flyers, excluded from transit rights given to Part 107/91/135", "No safety/security data cited to justify the rule", "Remote ID verification/logging requirement overburdens facility operators, invites litigation"]),
    "FAA-2026-4558-0448": ("drone_company", "support_with_changes", ["Preserve timely public-safety/emergency-response access within UAFRs", "Establish transparent, predictable approval process for authorized operators", "Keep restrictions narrow and risk-based"]),
    "FAA-2026-4558-0452": ("trade_association", "support", ["Financial sector supports petition-based framework over blanket prohibition", "Requests robust data-security handling of sensitive applicant vulnerability info", "Clarify institutions may still use drones for their own lawful security purposes"]),
    "FAA-2026-4558-0455": ("government_agency", "support", ["State DOTs support Section 2209 implementation and avoiding broad no-fly zones", "Managing vetted-operator access matters for DOT inspection/maintenance UAS use", "Supports FAA's burden-of-proof standard against over-designation"]),
    "FAA-2026-4558-0456": ("trade_association", "support_with_changes", ["Remove requirement that venues be TFR-ineligible to qualify for permanent UAFR", "Lower 2.5M annual attendance threshold to 200,000", "Lower 120-day open-to-public threshold to 60 days"]),
    "FAA-2026-4558-0460": ("media_photography", "oppose", ["Frames restriction as blocking documentation of animal agriculture/food production", "Public has a right to see where its food comes from", "Responsible drone photography serves transparency in the public interest"]),
    "FAA-2026-4558-0475": ("utility_water_energy", "support", ["LNG facilities are Critical Energy Infrastructure warranting drone prohibition", "Non-intrinsically-safe devices near gas processing pose ignition/upset risk", "Exception only for facility-hired commercial drones"]),
    "FAA-2026-4558-0480": ("other", "support_with_changes", ["Allow permanent UAFR regardless of TFR eligibility for smaller venue events", "Drop the 2.5M-attendance and 120-day thresholds; use 5,000-seat capacity instead", "Support 1,000-ft lateral buffer beyond property line; don't mandate formal security assessments"]),
    "FAA-2026-4558-0486": ("other", "support", ["Equine facilities should be eligible given horses' flight-response injury risk", "Drone disturbance risk spans breeding farms, racetracks, vet hospitals, competitions", "Recognize livestock/animal safety as a UAFR eligibility consideration"]),
    "FAA-2026-4558-0487": ("media_photography", "oppose", ["Frames rule as extreme First Amendment restriction", "Drones shouldn't be restricted to hide industrial animal agriculture practices"]),
    "FAA-2026-4558-0488": ("cuas_vendor", "support_with_changes", ["Strongly supports Part 74 framework structurally", "Require machine-readable UAFR data publication (cites EUROCAE ED-269/ED-318 standards)", "Draws on LAANC USS experience for UAFR access-workflow design"]),
    "FAA-2026-4558-0491": ("public_safety", "support_with_changes", ["NPRM too narrowly limits Healthcare sector eligibility to Level I trauma centers", "Include Stroke/STEMI/Burn centers and HAA helipads/emergency landing zones as CI", "Convene FAA stakeholder group on UAS/air-medical deconfliction before finalizing"]),
    "FAA-2026-4558-0492": ("drone_company", "support_with_changes", ["Continue allowing Part 137 agricultural drone operations within UAFRs", "Avoid broad inclusion of production agriculture in future Food & Ag Sector criteria", "Limit future ag UAFR eligibility to nationally/regionally significant facilities (grain terminals, strategic reserves)"]),
    "FAA-2026-4558-0493": ("cuas_vendor", "support", ["Strongly supports Remote ID sensing precondition and two-tier Standard/Special structure", "Validated sensor-fusion detection platform (Remote ID + radar) at MITRE test", "Supports five-year UAFR term with periodic renewal review"]),
    "FAA-2026-4558-0502": ("cuas_vendor", "support_with_changes", ["Strongly supports continued Special UAFR protections for nuclear/energy sites", "Requests extending vertical boundary to 1,200 ft AGL and lateral buffer beyond property lines", "Requests active sUAS monitoring/detection with law-enforcement Authority to Act, including jamming"]),

    # --- Batch reviewed 2026-07-07: post-comment-period-close surge ---
    "FAA-2026-4558-0517": ("individual_part107_operator", "support_with_changes", ["Small drone-photography business warns of cumulative restricted-area burden", "Narrowly tailor restrictions to demonstrated need with periodic review", "Requests FAA conduct a Small Business Impact Analysis"]),
    "FAA-2026-4558-0524": ("individual_part107_operator", "support_with_changes", ["Questions whether notification requirements actually deter malicious operators vs. burden compliant ones", "Asks FAA to clarify consistent facility-level administration of notification requests", "Focus regulatory effort on detection/response to unauthorized ops, not paperwork for compliant operators"]),
    "FAA-2026-4558-0551": ("trade_association", "support", ["Poultry trade group supports rule for biosecurity (HPAI/NWS) and food-security reasons", "Activist groups increasingly use drones for surveillance/campaign footage against farms", "Urges expedited finalization; food/ag facilities should be eligible for UAFR"]),
    "FAA-2026-4558-0554": ("government_agency", "support_with_changes", ["State Energy Offices (56 states/territories) support the § 74.88 energy-sector UAFR process, noting it mirrors threats already tracked in State Energy Security Plans", "Clarify how State Energy Office risk assessments (developed with DOE) will inform federal sponsorship/evaluation of energy-sector Special UAFRs", "Clarify how the federal framework interacts with existing state UAS-over-critical-infrastructure statutes and State Energy Security Plan measures"]),
    "FAA-2026-4558-0505": ("drone_company", "support_with_changes", ["Preserve clear, scalable access for certificated Part 107 operators, distinct from anonymous/malicious operators", "Clarify that authorized non-transitory work (hovering, orbiting, mapping) is permitted, not just transit", "Establish a standardized digital notification/whitelist pathway for repeat and pre-approved operators"]),
    "FAA-2026-4558-0549": ("trade_association", "support", ["Poultry trade group supports rule for biosecurity (HPAI) and food-security reasons", "Activist drone campaigns over poultry houses stress birds and risk disease-transmission via cross-farm flights", "Urges expedited finalization"]),
    "FAA-2026-4558-0550": ("critical_infrastructure_owner", "support_with_changes", ["Public power/irrigation district (dams + energy sector) supports the UAFR framework", "Preserve facility operators' own UAS use for FERC-mandated dam-safety inspections without case-by-case authorization", "Allow consolidated applications for commonly-owned multi-site systems; harmonize Part 74 with existing FERC oversight"]),
    "FAA-2026-4558-0534": ("individual_part107_operator", "oppose", ["Opposes the advance-notice transit requirement for certified Part 107 pilots specifically", "Argues administrative burden falls on vetted operators while doing nothing to deter bad actors", "Proposes a Remote ID protocol extension broadcasting verified Part 107 status instead of manual notification"]),
    "FAA-2026-4558-0556": ("trade_association", "support_with_changes", ["Telecom standards body (ATIS) flags mobile-network-based identity/tracking as a complement to Remote ID", "Highlights its USEC and ISAC-DI workstreams as future technical resources for UAFR access/enforcement", "Not proposing specific regulatory text at this stage; requests FAA engagement with its UAV Initiative"]),
    "FAA-2026-4558-0513": ("individual_part107_operator", "oppose", ["Cannot support rule as written: § 74.54 adopts the broad 16-sector NSM-22 framework instead of the narrower facility list Congress enumerated in 2209", "Proposes two-tier eligibility: automatic for Congress-enumerated sectors, heightened 'demonstration of cause' for all other NSM-22 sectors", "'Shortest practicable time' transit standard doesn't accommodate non-transitory mapping/inspection work; no defined max response time for facility notification"]),
    "FAA-2026-4558-0530": ("individual_other", "support", ["Cattle operation reports near-weekly unauthorized/BVLOS/nighttime drone activity and an activist drone-triggered stampede injuring livestock", "No current legal mechanism to stop activist surveillance filmed without consent", "Urges designating agricultural livestock facilities as eligible fixed-site facilities with enhanced BVLOS/nighttime penalties"]),
    "FAA-2026-4558-0510": ("drone_company", "support_with_changes", ["Large-UAS/AAM cargo operator (Cessna 208B autonomy STC) says § 74.250 access provisions only contemplate small UAS", "Aircraft with ATC-assigned transponder code and two-way ATC communication should be exempt from Remote ID/notification requirements as duplicative", "Proposes specific text amendments to §§ 74.250(a)(1) and 74.255"]),
    "FAA-2026-4558-0507": ("critical_infrastructure_owner", "support_with_changes", ["Joint filing from Ports of LA, Long Beach, and Oakland: property-line limitation leaves waterside approaches over channels/basins/slips unprotected since ports don't own adjacent navigable waters", "Allow a single consolidated UAFR per port complex instead of tenant-by-tenant applications under the landlord model", "Recognize existing MTSA Facility Security Assessments and Coast Guard Area Maritime Security Assessments as sufficient for Special UAFR eligibility, rather than requiring duplicative FAA-specific assessments"]),
}

# Campaign stragglers: clearly railroad-worker grievance but missing keywords
CAMPAIGN_IDS = {
    "FAA-2026-4558-0206", "FAA-2026-4558-0237", "FAA-2026-4558-0259",
    "FAA-2026-4558-0324", "FAA-2026-4558-0337", "FAA-2026-4558-0381",
}

# Railroad-labor campaign detector ------------------------------------------
# Strong terms are decisive on their own in this docket; weak terms need a
# worker-grievance frame to avoid false positives (e.g. "my backyard").
STRONG_RAIL = re.compile(r"\b(railroad(er|ing)?|railway|rail ?yard|switch(ing|man|men)|conductor|locomotive|brakeman|hump yard|shov(e|ing)|csx|union pacific|norfolk southern|bnsf|smart-?td|trainmaster|tank car|o-?test|operational test(ing)?|derail|hazmat)\b", re.I)
WEAK_RAIL = re.compile(r"\b(rail|train(s)?|crew|engineer|yard)\b", re.I)
WORKER_FRAME = re.compile(r"\b(distract|surveil|watch(ed|ing)?|spy|spie|discipl|fire(d|s)?|terminat|monitor|harass|intimidat|focus|attention|management|manager|officer|test(ed|ing)?|safety)\b", re.I)
# Personal worker-grievance language (no policy framing) — the unmistakable
# voice of the write-in campaign even when no rail noun appears.
GRIEVANCE = re.compile(r"(distract|being (watched|observed)|look(ing)? (up|around|at the sky)|take(s)? my focus|focus off|test you|spy(ing)? on|watch(ing)? (us|me|employee)|over our heads|as an? employee)", re.I)
POLICY_VOCAB = re.compile(r"\b(uafr|part 107|laanc|eligib|petition|boundary|boundaries|preempt|remote id|infrastructure|altitude|400 ?f(ee)?t|first amendment|small business|waiver|sector|navigable airspace|property line)\b", re.I)
OPPOSE_HINT = re.compile(r"\b(oppose|withdraw|reject|overreach|unconstitutional|public airspace|already (regulated|covered|illegal)|patchwork|privatiz)", re.I)
SWC_HINT = re.compile(r"\b(however|but |recommend|suggest|should|request|revise|refin|carve|exempt|provided that|as long as|streamlin)", re.I)

CATEGORY_LABELS = {
    "railroad_labor": "Railroad labor (write-in campaign)",
    "labor_union": "Labor unions (official filings)",
    "critical_infrastructure_owner": "Critical infrastructure owners",
    "utility_water_energy": "Utilities (water / energy)",
    "drone_company": "Drone companies",
    "individual_part107_operator": "Part 107 operators",
    "trade_association": "Trade associations",
    "cuas_vendor": "C-UAS / detection vendors",
    "media_photography": "Media / photography",
    "public_safety": "Public safety",
    "government_agency": "Government agencies",
    "academic": "Academic / test sites",
    "individual_hobbyist": "Hobbyists",
    "individual_other": "Other individuals",
    "other": "Other",
}


def is_campaign(text):
    t = text or ""
    if len(t) < 20:
        return False
    if STRONG_RAIL.search(t):
        return True
    if WEAK_RAIL.search(t) and WORKER_FRAME.search(t):
        return True
    # Generic worker-grievance with no policy vocabulary = campaign voice
    if GRIEVANCE.search(t) and not POLICY_VOCAB.search(t) and len(t) < 700:
        return True
    return False


def fallback_position(text):
    t = text or ""
    if OPPOSE_HINT.search(t):
        return "oppose"
    if SWC_HINT.search(t):
        return "support_with_changes"
    return "support"


def classify(c):
    cid = c["id"]
    text = c.get("comment_text", "") or ""
    if cid in CURATED:
        cat, pos, args = CURATED[cid]
        return cat, pos, args, True
    if cid in CAMPAIGN_IDS or is_campaign(text):
        return "railroad_labor", "support", [], False
    # Non-campaign, non-curated individual
    low = text.lower()
    if "hobby" in low or "recreational" in low:
        cat = "individual_hobbyist"
    else:
        cat = "individual_other"
    return cat, fallback_position(text), [], False


def iso_week(date_str):
    try:
        d = datetime.fromisoformat(date_str[:10])
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}", d
    except Exception:
        return None, None


def main():
    data = json.loads(COMMENTS.read_text(encoding="utf-8"))
    comments = data["comments"]

    positions_all = Counter()
    positions_ex = Counter()
    categories = Counter()
    themes = Counter()
    weekly = defaultdict(int)
    week_dates = {}
    notable = []
    unreviewed = []
    campaign_count = 0

    for c in comments:
        cat, pos, args, curated = classify(c)
        is_camp = (cat == "railroad_labor")
        if is_camp:
            campaign_count += 1
        # Surface new substantive org filings that haven't been hand-reviewed yet
        if not curated and not is_camp and (c.get("organization") or "").strip():
            unreviewed.append({
                "id": c["id"],
                "org": c.get("organization", ""),
                "date": (c.get("posted_date", "") or "")[:10],
                "url": c.get("url", ""),
            })
        positions_all[pos] += 1
        if not is_camp:
            positions_ex[pos] += 1
        categories[cat] += 1

        wk, d = iso_week(c.get("posted_date", ""))
        if wk:
            weekly[wk] += 1
            week_dates[wk] = d.strftime("%b %d")

        if curated:
            notable.append({
                "id": c["id"],
                "name": c.get("commenter", ""),
                "org": c.get("organization", ""),
                "category": cat,
                "position": pos,
                "arguments": args,
                "url": c.get("url", ""),
            })

    # theme frequency from curated arguments + lightweight text scan for campaign
    THEME_KEYWORDS = {
        "Access pathway / LAANC": r"laanc|access|notif|authoriz|approval|deviation|whitelist",
        "Patchwork / no-fly zones": r"patchwork|no-?fly|exclusion zone|fragment|swiss cheese",
        "Facility eligibility scope": r"eligib|critical infrastructure|sector|125,?000|which (sites|facilities)|data center|stadium|amusement",
        "Boundaries / altitude": r"property line|400 ?f(ee)?t|altitude|lateral|boundary|footprint",
        "Federal preemption": r"preempt|state law|federal|patch.*state",
        "Remote ID / detection gap": r"remote id|non-?cooperative|passive|detection|cannot detect",
        "Counter-UAS / mitigation": r"counter-?drone|c-?uas|jam|mitigat|disable|capture|shoot",
        "First Amendment / media": r"first amendment|newsgather|journalis|press|photograph",
        "Small business / cost": r"small business|cost|burden|economic|ria|irfa",
        "Contractor / owner gap": r"contractor|hired|owner|asset owner|sponsor",
        "Privacy / surveillance": r"privacy|surveil|spy|watch|monitor|discipl",
        "Transparency / publication": r"publish|machine-?readable|map|b4ufly|transparen|foia|confidential",
        "National security / threat": r"national security|terror|weapon|hazmat|attack|threat",
        "Overreach / withdraw": r"overreach|withdraw|reject|unconstitutional|public airspace",
    }
    compiled = {k: re.compile(v, re.I) for k, v in THEME_KEYWORDS.items()}
    for c in comments:
        t = c.get("comment_text", "") or ""
        for label, rx in compiled.items():
            if rx.search(t):
                themes[label] += 1

    timeline = [{"week": wk, "label": week_dates[wk], "count": weekly[wk]}
                for wk in sorted(weekly)]

    cat_sorted = [{"key": k, "label": CATEGORY_LABELS.get(k, k), "count": v}
                  for k, v in categories.most_common()]
    theme_sorted = [{"label": k, "count": v} for k, v in themes.most_common()]

    # priority ordering for notable display
    cat_priority = ["critical_infrastructure_owner", "utility_water_energy", "drone_company",
                    "individual_part107_operator", "cuas_vendor", "media_photography",
                    "government_agency", "public_safety", "trade_association", "academic",
                    "labor_union", "individual_hobbyist", "individual_other", "other"]
    notable.sort(key=lambda n: (cat_priority.index(n["category"]) if n["category"] in cat_priority else 99, n["id"]))

    # ----------------------------------------------------------------------
    # Curated analytical synthesis for AUVSI's draft
    # ----------------------------------------------------------------------
    takeaways = [
        {"title": "The volume is a labor write-in campaign, not 2209 endorsement",
         "body": f"About {round(campaign_count/len(comments)*100)}% of comments ({campaign_count} of {len(comments)}) are railroad workers (SMART-TD members, conductors, engineers, switchmen) protesting their OWN employers' use of drones for crew surveillance and discipline. They 'support restricting drones' but the target is employer 'operational testing,' not the external-threat problem Section 2209 addresses. Treat the raw support count as noise, not signal."},
        {"title": "Genuine 2209 stakeholders split into a predictable map",
         "body": "Infrastructure & utility owners SUPPORT (and want more). Commercial operators, surveyors and Part 107 pilots SUPPORT-WITH-CHANGES, all demanding automated access. C-UAS vendors want passive detection recognized. Media and hobbyists OPPOSE on First Amendment / airspace-privatization grounds. State DOTs want their authority preserved."},
        {"title": "Near-unanimous industry ask: LAANC-style automated access",
         "body": "Every commercial operator, surveyor, and most Part 107 commenters converge on the same fix: a LAANC-style notify-and-fly pathway, a contractor/owner authorization route, machine-readable real-time UAFR boundaries, and evidence-based narrow zones. This is AUVSI's strongest coalition position and is well-documented in the record."},
        {"title": "'De facto no-fly zone / patchwork' is the dominant operator fear",
         "body": "Operators repeatedly warn that a process that technically allows access but requires unclear approvals or manual coordination becomes a no-fly zone in practice — especially in dense regions (NJ) and along linear assets (rail, pipeline). Several supporters echo it. Anchor AUVSI's comment here."},
    ]

    flags = [
        {"severity": "high", "title": "Don't let FAA cite 'overwhelming support'",
         "body": "If FAA tallies raw counts, ~3 in 4 comments read as support — but that majority is an off-topic labor-surveillance grievance. AUVSI should explicitly name the campaign in the record so the genuine 2209 stakeholder split (far more divided, wanting guardrails) isn't drowned out.",
         "ids": ["FAA-2026-4558-0416"]},
        {"severity": "high", "title": "Counter-UAS / mitigation creep is out of scope and legally fraught",
         "body": "Multiple infrastructure commenters want the rule to authorize active mitigation — Middlesex Water explicitly asks for jamming and capture authority. Section 2209 is an airspace-restriction tool, not C-UAS authorization (which only limited federal agencies hold). AUVSI should flag the conflation and keep cUAS authority separate.",
         "ids": ["FAA-2026-4558-0217", "FAA-2026-4558-0051", "FAA-2026-4558-0353"]},
        {"severity": "high", "title": "Eligibility scope creep -> cumulative airspace loss",
         "body": "Commenters want everything in: amusement parks, schools, stadiums, hospitals, all water systems, ports, every rail bridge and tunnel. With 125,000+ potential sites, the cumulative effect threatens BVLOS scalability. Push for narrow, quantitative, evidence-based eligibility and a demonstrated-threat requirement to block frivolous/anti-competitive petitions.",
         "ids": ["FAA-2026-4558-0035", "FAA-2026-4558-0152", "FAA-2026-4558-0073", "FAA-2026-4558-0351"]},
        {"severity": "high", "title": "Comment period extended to August 5 — docket still open",
         "body": "The FAA granted the NY Attorney General's requested 30-day extension. The comment period now runs through August 5, 2026 (originally July 6). AUVSI's filing timeline should target the new deadline, and this dashboard's counts should be treated as a snapshot rather than a final tally until the docket actually closes.",
         "ids": ["FAA-2026-4558-0417"]},
        {"severity": "medium", "title": "Preemption is contested from both sides",
         "body": "Operators want STRONG federal preemption (uniform framework, machine-readable data). State DOTs (Virginia, Montana) want to PRESERVE authority over right-of-way and state drone laws. AUVSI's preemption position must thread this; note state-law spillover (e.g., Ohio HB77).",
         "ids": ["FAA-2026-4558-0419", "FAA-2026-4558-0353", "FAA-2026-4558-0356"]},
        {"severity": "medium", "title": "Remote ID can't validate non-cooperative aircraft",
         "body": "C-UAS vendors (Eldaeon, HUNTRAK) and HEMS/public-safety commenters note Remote ID alone can't distinguish a compliant transit from a non-cooperative threat. If AUVSI backs a Remote-ID-based whitelist/access mechanism, address the detection-gap critique directly.",
         "ids": ["FAA-2026-4558-0285", "FAA-2026-4558-0387", "FAA-2026-4558-0240"]},
        {"severity": "medium", "title": "Transparency vs. confidentiality tension",
         "body": "Operators demand UAFR boundaries published simultaneously in B4UFLY/LAANC; infrastructure owners want petitions FOIA-exempt to protect vulnerability data. These are reconcilable — support published boundaries while protecting the underlying threat justification — but AUVSI should say so explicitly.",
         "ids": ["FAA-2026-4558-0323", "FAA-2026-4558-0022"]},
        {"severity": "low", "title": "Process-legitimacy attack in the record",
         "body": "At least one commenter frames the rule as DJI-lobby-driven and demands a FARA investigation. Low signal, but be aware it's in the docket if the rulemaking's motivation is questioned.",
         "ids": ["FAA-2026-4558-0210"]},
    ]

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "total": len(comments),
        "campaign_count": campaign_count,
        "campaign_pct": round(campaign_count / len(comments) * 100),
        "positions_all": dict(positions_all),
        "positions_ex_campaign": dict(positions_ex),
        "categories": cat_sorted,
        "themes": theme_sorted,
        "timeline": timeline,
        "notable": notable,
        "unreviewed": unreviewed,
        "takeaways": takeaways,
        "flags": flags,
        "method_note": "Substantive 2209 stakeholder comments are hand-verified; the railroad-labor campaign and remaining individuals are detected programmatically and update as new comments arrive.",
    }

    OUT.write_text("const ANALYSIS_DATA = " + json.dumps(out, indent=2, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Wrote analysis for {len(comments)} comments -> {OUT.name}", file=sys.stderr)
    print(f"  Campaign: {campaign_count} ({out['campaign_pct']}%)", file=sys.stderr)
    print(f"  Positions (all): {dict(positions_all)}", file=sys.stderr)
    print(f"  Positions (ex-campaign): {dict(positions_ex)}", file=sys.stderr)
    print(f"  Curated notable: {len(notable)}", file=sys.stderr)


if __name__ == "__main__":
    main()
