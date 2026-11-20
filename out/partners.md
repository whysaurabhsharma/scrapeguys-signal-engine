# Partner archetypes - DRAFT - NOT SENT

## The conflict this run surfaced
The highest-reach channel is the incumbent we would replace. The Gramiyaa
brief pitches against Nitro Commerce; Nitro is also the top-ranked channel.
Sending that brief forecloses the channel. This is an ORDERING question,
not a binary: partner conversations are slower and higher-leverage, account
conversations faster and smaller. If Nitro is wanted as a channel, talk to
Nitro before pitching its customer. The Gramiyaa brief is held, not killed.

Run date: 2026-11-20. Source run: hunts 1-4, data/killlist.csv (58 rows), three incumbents found in staging notes.

**Partners are NOT accounts.** Nothing in this file is written to data/staging/, accounts.csv, signals.csv or scored.csv. No partner is scored. No partner is contacted.

---

## Finding (read this first)

1. **The best channel is the incumbent we are trying to displace.** Two of our three commerce incumbents (GobbleCube at Farmley, Nitro Commerce at Gramiyaa) are analytics layers, not collectors. They pass the partner test below. One conversation with either reaches its whole brand roster, and their case studies are where we found the buyers in the first place (scope.md section 9).
2. **The third incumbent is a competitor.** PromptCloud at Treebo sells the collection itself. Displace it; never partner with it.
3. **This creates a conflict a human must decide.** The Gramiyaa brief (out/briefs/ac_d0d2996d75-gramiyaa.md) positions against Nitro. Sending it closes the Nitro channel. Recommendation: hold the Gramiyaa brief until a decision on Nitro as partner.
4. **Of 26 vendor or suppressed kill-list rows, 15 are competitors, 3 are partner candidates, 1 is neither on current evidence, 7 cannot be classified** (hunt 1 recorded no source).

---

## The test: competitor or partner

> **If the live feed were handed to their customer for free, would that customer still pay them?**
>
> - **No** - the collection *is* what they sell. **Competitor.** Disqualified as partner (CLAUDE.md, STEP 5).
> - **Yes** - they sell a decision, workflow or service, and the feed is a cost of goods inside it. **Partner candidate.**

A second check stops the test being gamed: **what does their customer's invoice say?** "Rate shopping", "price monitoring", "data API", "crawl credits" = competitor. "Revenue management", "ads managed", "replenishment", "account management" = partner candidate.

Edge case, stated plainly: a partner candidate that already runs its own scrapers is also a *buyer* of the feed. That is the white-label motion, not a contradiction.

---

## Applying the test to the run's own evidence

### The three incumbents

| Incumbent | At | What their customer pays for | Verdict |
|---|---|---|---|
| PromptCloud | Treebo ([case study](https://www.promptcloud.com/blog/customer-spotlight-treebo/)) | Managed web-scraping service | **Competitor.** Displace. |
| GobbleCube | Farmley ([case study](https://gobblecube.ai/blog/stocking-smart-scaling-fast-behind-farmleys-insights-driven-growth-story)) | Revenue analytics and growth co-pilot for brands on Blinkit, Zepto, Instamart, Amazon ([Inc42](https://inc42.com/buzz/gobblecube-nets-15-mn-to-help-brands-scale-on-digital-marketplaces/)) | **Partner candidate.** Whether it collects in-house: UNVERIFIED. |
| Nitro Commerce | Gramiyaa ([Inc42](https://inc42.com/startups/why-gramiyaa-had-to-think-like-a-supermarket-to-win-on-quick-commerce/)) | Quick-commerce ads managed, paid on sales delivered; "Zodiac by Nitro" copilot ([Nitro blog](https://nitrocommerce.ai/blog/nitro-acquires-zodiac-quick-commerce-ai-copilot)) | **Partner candidate.** Says it tracks SKUs at pin-code level, so likely collects in-house: UNVERIFIED. |

### The kill list (26 vendor or suppressed rows)

| Verdict | Companies | Why |
|---|---|---|
| **Competitor** (15) | Wynd Labs, Firecrawl, Infatica, SearchApi, Exa, Similarweb, YipitData, Adthena, Babel Street, Lighthouse, Transparent, AirDNA, ApartmentIQ, WISEcode, Pricefy | The data or the crawl is the invoice line. Lighthouse sells exactly the travel ICP's parity pain. Pricefy sells exactly the commerce ICP's price monitoring. |
| **Partner candidate** (3) | RoomPriceGenie, Wayvia, aCommerce | Sells pricing decisions (RoomPriceGenie) or marketplace services (Wayvia, aCommerce). Competitor rates or shelf data are an input. These were correctly killed as *accounts* and are correctly kept as *partners*. |
| **Neither, on evidence** (1) | Alloy.ai | Killed as "retail data vendor". No source shows it needs a public-web feed. Not promoted without one. |
| **Cannot classify** (7) | MeasureOne, Sixtyfour, Parallel.ai, Kadoa, Source.ai, Datamint, Coast | Hunt 1 recorded no domain or source. The test needs a source. Left blank, not guessed. |

Pattern (wrong_buyer, not a vendor row) fails the test on its brand-protection line: it sells monitoring of "hundreds of websites daily" ([S-1](https://www.sec.gov/Archives/edgar/data/1811935/000162828025041036/pattern-sx1.htm)). Competitor there.

---

## The archetypes

### 1. Quick-commerce analytics copilots

- **Examples:** GobbleCube ([gobblecube.ai](https://gobblecube.ai/blog/journey-towards-simplifying-analytics-for-brands)), Nitro Commerce / Zodiac ([zodiac.nitrocommerce.ai](https://zodiac.nitrocommerce.ai/)).
- **Who they serve, how many:** consumer brands selling on Blinkit, Zepto, Instamart. GobbleCube client count UNVERIFIED. Nitro's press says "a network of over 2,500 brands" ([CXO Digital Pulse](https://www.cxodigitalpulse.com/nitro-commerce-acquires-zodiac-labs-ai-to-strengthen-quick-commerce-analytics/)), self-reported and for its whole D2C business; its quick-commerce customer count is UNVERIFIED.
- **What they do instead, why it hurts:** collect shelf data themselves, or rely on platform data. Platform data shows a brand its own sales, not competitors' price, rank and stock per pincode. Zepto now sells its own analytics, Zepto Atom ([Third Eyesight](https://www.thirdeyesight.in/zepto-atom-new-data-analytics-tool/)), which cuts into the platform-data half of their product and pushes their value onto the public-shelf half. Our probe got challenge pages from Instamart and Zepto and a 403 from Blinkit for a plain client (out/assets/commerce-2026-11-20.md). Whether they face the same at their scale: UNVERIFIED.
- **What they would buy:** a pincode-level live feed of price, rank and stock on the three platforms, running inside their dashboard.
- **First objection:** "We already collect this ourselves."
- **Mode: white-label.** The brand buys their dashboard, not our feed. Our name would only add a second vendor to the brand's procurement.

### 2. Hotel revenue-management software for independent hotels

- **Examples:** RoomPriceGenie ([roompricegenie.com](https://roompricegenie.com/ai-info/), on kill list as vendor), Hotel Superhero by Treebo ([hotelsuperhero.com](https://www.hotelsuperhero.com/)).
- **Who they serve, how many:** independent hotels without a full-time revenue manager. RoomPriceGenie client count UNVERIFIED. Hotel Superhero client count UNVERIFIED.
- **What they do instead, why it hurts:** RoomPriceGenie's own guides say its product gives "daily updates on competitor rates" ([guide](https://roompricegenie.com/set-room-prices-beat-competition/)). Where those rates come from: UNVERIFIED. If they come from a rate-intelligence vendor such as Lighthouse, that supplier is also a direct competitor in their market.
- **What they would buy:** the comp-set and OTA rate feed under their pricing engine, at a frequency above daily.
- **First objection:** "Our rate data is already good enough, and switching supplier risks every customer's prices."
- **Mode: white-label.** The hotel buys a price recommendation. The feed is invisible.
- **Run-specific note:** Treebo is a Tier-scored *account* (PromptCloud incumbent) and also sells Hotel Superhero to independents ([Hospibuz](https://hospibuz.com/hot-topics/thv-launches-its-ai-powered-hotel-management-system-hotel-superhero-as-a-saas-offering-for-independent-hotels-10519486)). Winning Treebo as a buyer could open this channel. The account stays in the pipeline; the channel stays here.

### 3. Quick-commerce and marketplace agencies

- **Examples:** SW Cybernetics ([swcybernetics.in](https://swcybernetics.in/services/quick-commerce-agency)), Wayvia ([posting](https://job-boards.greenhouse.io/wayvia/jobs/8085399002), kill list), aCommerce ([posting](https://job-boards.greenhouse.io/acommerce/jobs/8132005), kill list).
- **Who they serve, how many:** D2C brands launching on and running quick-commerce or marketplace accounts. SW Cybernetics claims "150+ brands onboarded" on Zepto ([page](https://swcybernetics.in/services/zepto-marketing-agency)), self-reported. Wayvia and aCommerce counts UNVERIFIED.
- **What they do instead, why it hurts:** people check listings by hand. The run found the same manual loop at a brand: Gramiyaa's "intern manually checked pin codes" ([Inc42](https://inc42.com/startups/why-gramiyaa-had-to-think-like-a-supermarket-to-win-on-quick-commerce/)). Whether agencies do this for clients: UNVERIFIED.
- **What they would refer:** a live shelf-visibility feed to the brands they already manage.
- **First objection:** "Our clients already pay a dashboard vendor."
- **Mode: refer.** Agencies sell hours, not software. They would not carry a data contract.

### 4. Brand-protection and MAP-enforcement services

- **Examples:** Red Points ([redpoints.com](https://www.redpoints.com/?p=15262)), MarqVision ([guide](https://www.marqvision.com/guide/identify-third-party-sellers-violating-map-policies)).
- **Who they serve, how many:** manufacturers fighting unauthorised sellers and below-MAP listings. Counts UNVERIFIED.
- **Run evidence of the end demand:** MAP and pricing-violation roles at Chervon, Antelope and Fortune Brands, and a staffing agency (MultiplyMii) hiring human MAP monitors for unnamed clients ([posting](https://jobs.ashbyhq.com/multiplymii/d5fa10cc-4b38-4911-83f7-4cba393a9c71)). All killed for no dated signal or wrong buyer. The pain is real; the brands were not reachable inside the 90-day window.
- **What they do instead:** automated scans plus human review, per vendor marketing. Whether they crawl in-house: UNVERIFIED, probably yes.
- **What they would buy:** marketplace listing coverage they do not reach, sold as an input to takedowns.
- **First objection:** "Crawling is our moat."
- **Mode: white-label,** only where they buy coverage. Wiser and TrackStreet sell the monitoring itself ([Wiser](https://wiser.com/map-monitoring), [TrackStreet](https://www.trackstreet.com/lp-map-enforcement)): **competitors**, excluded.

### Considered, not included

Hotel distribution consultants, AI application builders, data consultancies, ERP integrators. The run produced no evidence for any of them. The AI ICP turned up buyers (Going, Lyst and others) but no incumbent sitting between them and their data. Untested, not rejected.

---

## Ranking by reach per conversation

**1. Quick-commerce analytics copilots.** Highest. One signed partner puts the feed in front of every brand on their dashboard, with no further sale per brand. The run also proves they have reach into exactly our buyers: three commerce accounts (Farmley, Gramiyaa, Moms Home) were found through their case studies and co-produced content, after seed lists failed three times in four (scope.md section 9). Nitro's Inc42 series means it publishes its customers' pain for us. Two risks keep this from being a sure thing. They may already collect and see us as a supplier swap, not a gain. And partnering with either one closes the displacement brief at its customers. That conflict is the decision this file asks for.

**2. Hotel RMS for independents.** Second. Same white-label mechanics as rank 1: one conversation, many hotels, no per-hotel sale. Ranked below because (a) no RMS customer count was sourced, so the reach is asserted, not measured; (b) RMS buyers sell a *price recommendation*, while our travel ICP pain is *parity across OTAs*, so the fit is adjacent, not exact; (c) changing rate supplier touches every customer's prices at once, so the sales cycle is slower than an analytics vendor adding a coverage source. Treebo's Hotel Superhero lifts it above rank 3: a won account becomes a warm channel.

**3. Quick-commerce and marketplace agencies.** Third. The raw number of brands per agency may match rank 1 (SW Cybernetics claims 150+). But a referral is an introduction, not a deployment: each brand still needs its own sale, its own budget and its own sign-off. Reach per conversation is high in names and low in closed revenue. Agencies are also the natural channel *for* rank 1's dashboards, so we would be competing for the same referral.

**4. Brand-protection and MAP services.** Last. The end demand is real and was seen in the run four times. It ranks last for three reasons. It is mostly US marketplace work, outside the India quick-commerce focus where our evidence is strongest. The line between partner and competitor is thinnest here: two of the four vendors found sell monitoring outright. And the ones that pass the test probably treat crawling as their moat, so the first conversation starts at "no".

---

## Method

- Incumbents taken from staging notes for Treebo, Farmley, Gramiyaa, Moms Home. Kill list read in full (58 rows, 26 vendor or suppressed).
- Each vendor row classified by the test above using the reason and source already in data/killlist.csv. No row without a source was classified.
- Examples for archetypes 1, 3, 4 and RoomPriceGenie's role checked by web search on 2026-11-20. Vendor pages are self-reported; every count is marked as such or UNVERIFIED.
- Nothing written to any CSV or to data/staging/. Nothing sent.

**Waiting for the human on:** partner Nitro and GobbleCube, or send the displacement briefs. Not both.
