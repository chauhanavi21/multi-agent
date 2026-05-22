"""Run with: python -m app.db.init_db"""
from app.db.models import Base, engine, SessionLocal, Lead


SEED_LEADS = [
    {
        "name": "Priya Sharma",
        "title": "Head of Engineering",
        "company": "FlowPay",
        "industry": "Fintech",
        "email": "priya@flowpay.example",
        "notes": "Posted on LinkedIn about scaling payment infra to 10M users",
    },
    {
        "name": "Marcus Chen",
        "title": "VP of Product",
        "company": "Northwind Analytics",
        "industry": "B2B SaaS",
        "email": "marcus@northwind.example",
        "notes": "Looking for a dashboard solution; mentioned slow internal tools",
    },
    {
        "name": "Sara Okafor",
        "title": "CTO",
        "company": "Lumen Health",
        "industry": "Healthtech",
        "email": "sara@lumenhealth.example",
        "notes": "HIPAA-focused; building patient portal from scratch",
    },
    {
        "name": "Diego Alvarez",
        "title": "Director of Sales Ops",
        "company": "Tidewater Logistics",
        "industry": "Supply chain",
        "email": "diego@tidewater.example",
        "notes": "Frustrated with current CRM; team of 30 reps",
    },
    {
        "name": "Hana Tanaka",
        "title": "Founder",
        "company": "Kasa Studios",
        "industry": "Design agency",
        "email": "hana@kasa.example",
        "notes": "Newly funded seed round; hiring + brand expansion",
    },
]


def main():
    print("Dropping + recreating tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for row in SEED_LEADS:
            db.add(Lead(**row))
        db.commit()
        print(f"Seeded {len(SEED_LEADS)} leads.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
