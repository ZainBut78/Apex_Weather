"""Historical data ko target range tak poora karo — INCREMENTALLY.

Yeh command saal mein ek dafa cron/pm2 se chalne ke liye bani hai. Jab naya
saal aata hai, target range ek saal aage khisak jati hai, aur yeh command
**sirf us naye saal** ke liye Open-Meteo ko call karti hai. Jo data pehle
se DB mein hai woh dobara fetch NAHI hota.

Misaal (HISTORICAL_YEARS=20):
    2026 mein target = 2006-2025. DB mein 2006-2025 hai -> 0 API calls.
    2027 aaya, target = 2007-2026. DB mein 2026 nahi -> sirf 2026 ke
    liye 1 call per city.

Istemal:
    python manage.py sync_historical --dry-run      # sirf batao kya hoga
    python manage.py sync_historical                # missing saal fetch karo
    python manage.py sync_historical --city paris   # ek hi city
    python manage.py sync_historical --audit        # ghalat-unit rainfall dhoondo
    python manage.py sync_historical --rebuild --city paris   # delete + dobara fetch

Cron (saal mein ek dafa, 5 January):
    0 3 5 1 *  cd /path/to/Apex_Weather && venv/bin/python manage.py sync_historical
"""

import time

from django.core.management.base import BaseCommand, CommandError

from weather.historical import (
    cities_with_suspicious_rainfall,
    ensure_history,
    missing_year_blocks,
    target_year_range,
)
from weather.models import City, HistoricalWeather


class Command(BaseCommand):
    help = "Historical weather ko target range tak poora karo (sirf missing saal fetch karta hai)"

    def add_arguments(self, parser):
        parser.add_argument("--city", type=str, default=None,
                            help="Sirf is slug wali city (warna saari cities)")
        parser.add_argument("--dry-run", action="store_true",
                            help="Kuch fetch na karo, sirf batao kya missing hai")
        parser.add_argument("--audit", action="store_true",
                            help="Woh cities dhoondo jinka rainfall purane (daily-average) formula se lagta hai")
        parser.add_argument("--rebuild", action="store_true",
                            help="Target range ka data DELETE karke dobara fetch karo (unit fix ke liye)")
        parser.add_argument("--sleep", type=float, default=12.0,
                            help="Do cities ke darmiyan itne second rukо (Open-Meteo ki etiquette). Default 12")
        parser.add_argument("--limit", type=int, default=None,
                            help="Sirf pehli N cities (testing ke liye)")

    def handle(self, *args, **opts):
        start_year, end_year = target_year_range()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Target range: {start_year}-{end_year}  ({end_year - start_year + 1} saal)"
        ))

        if opts["audit"]:
            return self._audit(start_year, end_year)

        cities = City.objects.all().order_by("slug")
        if opts["city"]:
            cities = cities.filter(slug=opts["city"])
            if not cities.exists():
                raise CommandError(f"City '{opts['city']}' nahi mili")
        if opts["limit"]:
            cities = cities[:opts["limit"]]

        total = cities.count() if hasattr(cities, "count") else len(cities)
        self.stdout.write(f"Cities: {total}\n")

        if opts["rebuild"] and not opts["city"] and not opts["dry_run"]:
            raise CommandError(
                "--rebuild saari cities pe ek sath chalane se bohot API calls jayengi. "
                "--city <slug> ke sath chalao, ya pehle --dry-run dekho."
            )

        needs_work = 0
        api_calls = 0
        rows_saved = 0
        failures = []

        for i, city in enumerate(cities, 1):
            if opts["rebuild"] and not opts["dry_run"]:
                deleted, _ = HistoricalWeather.objects.filter(
                    city=city, year__gte=start_year, year__lte=end_year
                ).delete()
                self.stdout.write(f"  [{i}/{total}] {city.slug}: {deleted} purani rows delete kiye (rebuild)")

            blocks = missing_year_blocks(city, start_year, end_year)
            if not blocks:
                continue

            needs_work += 1
            years_txt = ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in blocks)

            if opts["dry_run"]:
                self.stdout.write(
                    f"  [{i}/{total}] {city.slug:24} missing: {years_txt}   "
                    f"({len(blocks)} API call{'s' if len(blocks) > 1 else ''})"
                )
                api_calls += len(blocks)
                continue

            self.stdout.write(f"  [{i}/{total}] {city.slug:24} fetching: {years_txt} ...", ending="")
            self.stdout.flush()
            result = ensure_history(city, feature="weather",
                                    start_year=start_year, end_year=end_year)
            api_calls += result["api_calls"]
            rows_saved += result["rows_saved"]

            if result["complete"]:
                self.stdout.write(self.style.SUCCESS(f" OK ({result['rows_saved']} rows)"))
            else:
                failures.append(city.slug)
                self.stdout.write(self.style.ERROR(f" FAIL (baqi: {result['missing_after']})"))

            if opts["sleep"]:
                time.sleep(opts["sleep"])

        self.stdout.write("")
        verb = "lagti" if opts["dry_run"] else "lagi"
        self.stdout.write(self.style.MIGRATE_HEADING("Khulasa"))
        self.stdout.write(f"  cities jinhe kaam chahiye tha : {needs_work} / {total}")
        self.stdout.write(f"  Open-Meteo calls {verb}        : {api_calls}")
        if not opts["dry_run"]:
            self.stdout.write(f"  monthly rows likhe            : {rows_saved}")
            if failures:
                self.stdout.write(self.style.WARNING(
                    f"  fail hui cities ({len(failures)})       : {', '.join(failures[:12])}"
                    + (" ..." if len(failures) > 12 else "")
                ))
        if needs_work == 0:
            self.stdout.write(self.style.SUCCESS(
                "  Sab kuch already complete hai — ek bhi Open-Meteo call nahi gayi."
            ))

    # ──────────────────────────────────────────────────────────────
    def _audit(self, start_year, end_year):
        rows = cities_with_suspicious_rainfall(start_year, end_year)
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Rainfall unit audit — woh cities jinka data purane (daily-average) formula se lagta hai"
        ))
        if not rows:
            self.stdout.write(self.style.SUCCESS(
                "  Koi mashkook city nahi mili. Lagta hai sab monthly-total formula pe hai."
            ))
            return
        self.stdout.write(
            f"  {len(rows)} cities ka max monthly rainfall 15mm se kam hai — "
            f"yeh aam tor par daily-average ki nishani hai:\n"
        )
        for r in rows:
            self.stdout.write(
                f"    {r['city__slug']:26} {r['city__name']:22} max monthly rainfall = {r['max_rain']}mm"
            )
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "  NOTE: sachmuch sookhe elaqe (Aswan, Arica) bhi is list mein aa sakte hain —\n"
            "  yeh shubha hai, faisla nahi. Theek karne ke liye har city pe:\n"
            "      python manage.py sync_historical --rebuild --city <slug>"
        ))
