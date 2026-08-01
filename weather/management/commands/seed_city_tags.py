from django.core.management.base import BaseCommand
from weather.models import City

CITY_TAGS = [
    ("london", False, False), ("manchester", False, False),
    ("birmingham", False, False), ("edinburgh", True, True),
    ("glasgow", False, True),
    ("paris", False, False), ("lyon", False, False),
    ("marseille", True, False), ("toulouse", False, False),
    ("nice", True, True),
    ("berlin", False, False), ("munich", False, True),
    ("hamburg", True, False), ("frankfurt", False, False),
    ("cologne", False, False),
    ("madrid", False, False), ("barcelona", True, False),
    ("valencia", True, False), ("seville", False, False),
    ("bilbao", True, False),
    ("rome", False, False), ("milan", False, False),
    ("naples", True, False), ("turin", False, False),
    ("florence", False, False),
    ("amsterdam", True, False), ("rotterdam", True, False),
    ("the-hague", True, False),
    ("vienna", False, True), ("salzburg", False, True),
    ("brussels", False, False), ("antwerp", False, False),
    ("dublin", True, False), ("cork", True, False),
    ("lisbon", True, False), ("porto", True, False),
    ("stockholm", True, False), ("gothenburg", True, False),
    ("oslo", True, True), ("bergen", True, True), ("trondheim", True, False),
    ("copenhagen", True, False), ("aarhus", True, False),
    ("helsinki", True, False), ("tampere", False, False),
    ("warsaw", False, False), ("krakow", False, False), ("gdansk", True, False),
    ("prague", False, False), ("brno", False, False),
    ("budapest", False, False),
    ("athens", True, False), ("thessaloniki", True, False),
    ("istanbul", True, False), ("ankara", False, False), ("antalya", True, False),
    ("zurich", False, True), ("geneva", False, True),
    ("moscow", False, False), ("saint-petersburg", True, False),
    ("kazan", False, False), ("sochi", True, True),
    ("baku", True, False),
    ("new-york", True, False), ("los-angeles", True, False),
    ("chicago", True, False), ("houston", False, False),
    ("phoenix", False, False), ("philadelphia", False, False),
    ("san-antonio", False, False), ("san-diego", True, False),
    ("dallas", False, False), ("austin", False, False),
    ("san-francisco", True, False), ("seattle", True, True),
    ("denver", False, True), ("washington-dc", False, False),
    ("boston", True, False), ("nashville", False, False),
    ("portland", False, True), ("las-vegas", False, False),
    ("miami", True, False), ("atlanta", False, False),
    ("detroit", False, False), ("minneapolis", False, False),
    ("salt-lake-city", False, True), ("orlando", False, False),
    ("new-orleans", False, False), ("pittsburgh", False, False),
    ("honolulu", True, True),
    ("toronto", True, False), ("vancouver", True, True),
    ("montreal", False, False), ("calgary", False, True),
    ("lahore", False, False), ("karachi", True, False),
    ("islamabad", False, True), ("peshawar", False, False), ("quetta", False, False),
    ("mumbai", True, False), ("delhi", False, False),
    ("bangalore", False, False), ("chennai", True, False), ("kolkata", False, False),
    ("dhaka", False, False), ("chittagong", True, False),
    ("kathmandu", False, True), ("pokhara", False, True),
    ("colombo", True, False),
    ("manila", True, False), ("cebu", True, False),
    ("kuala-lumpur", False, False),
    ("hanoi", False, False), ("ho-chi-minh-city", False, False),
    ("yangon", False, False),
    ("tehran", False, True), ("isfahan", False, False), ("shiraz", False, False),
    ("beijing", False, False), ("shanghai", True, False),
    ("guangzhou", True, False), ("chengdu", False, False),
    ("shenzhen", True, False), ("hong-kong", True, True),
    ("tokyo", True, False), ("osaka", True, False), ("kyoto", False, True),
    ("seoul", False, False), ("busan", True, False),
    ("bali", True, True), ("jakarta", True, False),
    ("sydney", True, False), ("melbourne", True, False),
    ("brisbane", True, False), ("perth", True, False),
    ("dubai", True, False), ("abu-dhabi", True, False),
    ("sao-paulo", False, False), ("rio-de-janeiro", True, True),
    ("mexico-city", False, False), ("cancun", True, False),
    ("cape-town", True, True), ("johannesburg", False, False),
    ("bangkok", False, False), ("phuket", True, False),
    ("cairo", False, False), ("lagos", True, False),
    ("buenos-aires", True, False),
    ("auckland", True, False), ("wellington", True, False),
    ("bogota", False, False), ("medellin", False, False),
    ("quito", False, True), ("san-jose", False, False),
]

class Command(BaseCommand):
    help = "Tag cities with is_coastal / has_hiking_trails flags"

    def handle(self, *args, **kwargs):
        updated, missing = 0, []
        for slug, coastal, hiking in CITY_TAGS:
            count = City.objects.filter(slug=slug).update(
                is_coastal=coastal, has_hiking_trails=hiking
            )
            if count:
                updated += 1
            else:
                missing.append(slug)

        self.stdout.write(self.style.SUCCESS(f"Tagged {updated} cities"))
        if missing:
            self.stdout.write(self.style.WARNING(
                f"Slug not found in DB (check spelling): {missing}"
            ))
