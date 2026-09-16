from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '__first__'),
        ('contenttypes', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='NgoProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('address', models.TextField(blank=True, null=True)),
                ('city', models.CharField(blank=True, max_length=100, null=True)),
                ('specializations', models.JSONField(default=list)),
                ('ambulances', models.IntegerField(default=0)),
                ('boats', models.IntegerField(default=0)),
                ('fire_trucks', models.IntegerField(default=0)),
                ('volunteers', models.IntegerField(default=0)),
                ('is_verified', models.BooleanField(default=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='ngo_profile', to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('address', models.TextField(blank=True, null=True)),
                ('city', models.CharField(blank=True, max_length=100, null=True)),
                ('state', models.CharField(blank=True, max_length=100, null=True)),
                ('language', models.CharField(blank=True, max_length=100, null=True)),
                ('family_count', models.CharField(blank=True, default='0', max_length=50, null=True)),
                ('emergency_contact', models.CharField(blank=True, max_length=20, null=True)),
                ('medical_conditions', models.TextField(blank=True, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='user_profile', to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='Emergency',
            fields=[
                ('sosId', models.CharField(max_length=50, primary_key=True, serialize=False, unique=True)),
                ('disaster', models.CharField(max_length=50)),
                ('urgency', models.CharField(max_length=20)),
                ('name', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=20)),
                ('people', models.CharField(default='1', max_length=20)),
                ('description', models.TextField(blank=True, null=True)),
                ('latitude', models.FloatField(default=0.0)),
                ('longitude', models.FloatField(default=0.0)),
                ('status', models.CharField(choices=[('pending', 'Pending Dispatch'), ('accepted', 'Accepted / Dispatched'), ('arrived', 'Team Arrived'), ('resolved', 'Resolved & Closed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('eta', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('matched_ngo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='matched_emergencies', to='api.ngoprofile')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='emergencies', to='auth.user')),
            ],
        ),
    ]
