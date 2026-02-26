"""
Bulk DB update:
- Delete 12 invalid/acquired/closed companies (and their jobs)
- Update website_url for ~115 companies
"""
import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

COMPANIES_TO_DELETE = [
    "Canva Docs",
    "Determined AI",
    "Fetch Robotics",
    "Freshly",
    "Netlify CMS",
    "Nexmo",
    "Partytown",
    "Prospera Technologies",
    "Running Tide",
    "States Title",
    "Themis Solutions",
    "Twistlock",
]

WEBSITE_UPDATES = {
    "DoorDash": "https://www.doordash.com",
    "Epic Games": "https://www.epicgames.com",
    "Expedia": "https://www.expedia.com",
    "FIS": "https://www.fisglobal.com",
    "Global Payments": "https://www.globalpayments.com",
    "Intuit": "https://www.intuit.com",
    "OpenAI": "https://www.openai.com",
    "Reddit": "https://www.reddit.com",
    "SAP": "https://www.sap.com",
    "ServiceNow": "https://www.servicenow.com",
    "Tesla": "https://www.tesla.com",
    "UKG": "https://www.ukg.com",
    "xAI": "https://x.ai",
    "Adjust": "https://www.adjust.com",
    "Arrival": "https://arrival.com",
    "Babylon Health": "https://www.babylonhealth.com",
    "CoStar": "https://www.costar.com",
    "Coupa": "https://www.coupa.com",
    "Cursor": "https://www.cursor.com",
    "DataCamp": "https://www.datacamp.com",
    "Delivery Hero": "https://www.deliveryhero.com",
    "Dell Technologies": "https://www.dell.com",
    "Depop": "https://www.depop.com",
    "Doctolib": "https://www.doctolib.fr",
    "Drata": "https://www.drata.com",
    "Dutchie": "https://www.dutchie.com",
    "Embracer Group": "https://www.embracer.com",
    "Ericsson": "https://www.ericsson.com",
    "Etsy": "https://www.etsy.com",
    "Faire": "https://www.faire.com",
    "Farfetch": "https://www.farfetch.com",
    "Flipkart": "https://www.flipkart.com",
    "FREE NOW": "https://www.free-now.com",
    "Fundrise": "https://www.fundrise.com",
    "Getir": "https://www.getir.com",
    "GetYourGuide": "https://www.getyourguide.com",
    "GOAT": "https://www.goat.com",
    "GoodRx": "https://www.goodrx.com",
    "Gusto": "https://www.gusto.com",
    "HashiCorp": "https://www.hashicorp.com",
    "Hims": "https://www.forhims.com",
    "Hims & Hers": "https://www.forhims.com",
    "Hopper": "https://www.hopper.com",
    "Insomniac Games": "https://www.insomniacgames.com",
    "Jumia": "https://www.jumia.com",
    "Just Eat Takeaway": "https://www.justeattakeaway.com",
    "Klook": "https://www.klook.com",
    "Krafton": "https://www.krafton.com",
    "Kraken": "https://www.kraken.com",
    "Lime": "https://www.li.me",
    "Masterclass": "https://www.masterclass.com",
    "Meesho": "https://www.meesho.com",
    "Mercari": "https://www.mercari.com",
    "Midjourney": "https://www.midjourney.com",
    "NetApp": "https://www.netapp.com",
    "NIO": "https://www.nio.com",
    "Nykaa": "https://www.nykaa.com",
    "Ola": "https://www.olacabs.com",
    "Omio": "https://www.omio.com",
    "Patreon": "https://www.patreon.com",
    "Paystack": "https://paystack.com",
    "Perplexity": "https://www.perplexity.ai",
    "Personio": "https://www.personio.com",
    "Quizlet": "https://www.quizlet.com",
    "Revolut": "https://www.revolut.com",
    "SafetyCulture": "https://www.safetyculture.com",
    "Sage": "https://www.sage.com",
    "Showpad": "https://www.showpad.com",
    "Sitecore": "https://www.sitecore.com",
    "Skillshare": "https://www.skillshare.com",
    "SoFi": "https://www.sofi.com",
    "Square for Restaurants": "https://squareup.com/us/en/restaurants",
    "StockX": "https://www.stockx.com",
    "Substack": "https://www.substack.com",
    "Swan": "https://www.swan.io",
    "Swiggy": "https://www.swiggy.com",
    "Tableau": "https://www.tableau.com",
    "Thinkific": "https://www.thinkific.com",
    "ThredUp": "https://www.thredup.com",
    "Toast": "https://www.toasttab.com",
    "Tokopedia": "https://www.tokopedia.com",
    "Toptal": "https://www.toptal.com",
    "TripAdvisor": "https://www.tripadvisor.com",
    "TuSimple": "https://www.tusimple.com",
    "Udemy": "https://www.udemy.com",
    "Vestiaire Collective": "https://www.vestiairecollective.com",
    "Vivino": "https://www.vivino.com",
    "Vonage": "https://www.vonage.com",
    "Whatnot": "https://www.whatnot.com",
    "Zillow": "https://www.zillow.com",
    "Zocdoc": "https://www.zocdoc.com",
    "Africa's Talking": "https://africastalking.com",
    "Around": "https://www.around.co",
    "Contextual AI": "https://contextual.ai",
    "ConvertKit": "https://convertkit.com",
    "Cradle AI": "https://www.cradle.bio",
    "Culture Trip": "https://www.theculturetrip.com",
    "Feedvisor": "https://www.feedvisor.com",
    "Galileo AI": "https://www.usegalileo.ai",
    "Hawkeye 360": "https://www.he360.com",
    "Imbue": "https://imbue.com",
    "Magic AI": "https://magic.dev",
    "McMakler": "https://www.mcmakler.de",
    "Normalyze": "https://normalyze.ai",
    "Normative": "https://normative.io",
    "Panther Labs": "https://panther.com",
    "Plenty": "https://www.plenty.ag",
    "Poolside AI": "https://www.poolside.ai",
    "Ravio": "https://ravio.com",
    "Reka AI": "https://www.reka.ai",
    "Sifflet": "https://www.siffletdata.com",
    "Slite": "https://slite.com",
    "Solid Power": "https://www.solidpowerbattery.com",
    "Springboard": "https://www.springboard.com",
    "Sweep": "https://www.sweep.net",
    "TeamApt": "https://moniepoint.com",
    "Tome": "https://tome.app",
    "Tribal Credit": "https://www.tribal.credit",
    "Unstructured": "https://unstructured.io",
    "Zopa": "https://www.zopa.com",
}


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # ── 1. DELETE companies ────────────────────────────────────────────
        print("=== DELETIONS ===")
        for name in COMPANIES_TO_DELETE:
            # get company id first
            row = await conn.fetchrow("SELECT id FROM companies WHERE name = $1", name)
            if row is None:
                print(f"  [NOT FOUND] {name}")
                continue
            cid = row["id"]
            # delete jobs first (no cascade assumed)
            deleted_jobs = await conn.execute(
                "DELETE FROM jobs WHERE company_id = $1", cid
            )
            deleted_co = await conn.execute(
                "DELETE FROM companies WHERE id = $1", cid
            )
            print(f"  [DELETED] {name}  |  {deleted_jobs}  |  company: {deleted_co}")

        # ── 2. UPDATE website_url ──────────────────────────────────────────
        print("\n=== WEBSITE URL UPDATES ===")
        updated = 0
        not_found = []
        for name, url in WEBSITE_UPDATES.items():
            result = await conn.execute(
                "UPDATE companies SET website_url = $1 WHERE name = $2",
                url, name,
            )
            # result is like "UPDATE 1" or "UPDATE 0"
            count = int(result.split()[-1])
            if count:
                print(f"  [OK] {name}  →  {url}")
                updated += 1
            else:
                not_found.append(name)

        print(f"\nUpdated: {updated}/{len(WEBSITE_UPDATES)}")
        if not_found:
            print(f"Not found in DB ({len(not_found)}):")
            for n in not_found:
                print(f"  - {n}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
