from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("elections", "0001_initial")]
    operations = [migrations.CreateModel(name="Attendance", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("voter_code", models.CharField(max_length=120)), ("scanned_at", models.DateTimeField(auto_now_add=True)),
        ("election", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attendances", to="elections.election")),
        ("scanned_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
    ]), migrations.AddConstraint(model_name="attendance", constraint=models.UniqueConstraint(fields=("election", "voter_code"), name="unique_attendance_per_election")),
    migrations.AddIndex(model_name="attendance", index=models.Index(fields=["election", "voter_code"], name="attendance_electio_2d5382_idx")),]
