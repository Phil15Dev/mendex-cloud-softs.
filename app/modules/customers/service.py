from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Customer


def upsert_customer(db: Session, phone: str, name: str) -> Customer:
    cust = db.scalar(select(Customer).where(Customer.phone == phone))
    if cust is None:
        cust = Customer(phone=phone, name=name)
        db.add(cust)
        db.flush()
    else:
        cust.name = name  # latest name the customer gave
    return cust
