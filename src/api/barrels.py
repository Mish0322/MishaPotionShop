from dataclasses import dataclass
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List
import random

import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/barrels",
    tags=["barrels"],
    dependencies=[Depends(auth.get_api_key)],
)


class Barrel(BaseModel):
    sku: str
    ml_per_barrel: int = Field(gt=0, description="Must be greater than 0")
    potion_type: List[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d] that sum to 1.0",
    )
    price: int = Field(ge=0, description="Price must be non-negative")
    quantity: int = Field(ge=0, description="Quantity must be non-negative")

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[float]) -> List[float]:
        if len(potion_type) != 4:
            raise ValueError("potion_type must have exactly 4 elements: [r, g, b, d]")
        if not abs(sum(potion_type) - 1.0) < 1e-6:
            raise ValueError("Sum of potion_type values must be exactly 1.0")
        return potion_type


class BarrelOrder(BaseModel):
    sku: str
    quantity: int = Field(gt=0, description="Quantity must be greater than 0")


@dataclass
class BarrelSummary:
    gold_paid: int
    red_ml: int
    green_ml: int
    blue_ml: int    

#def calculate_barrel_summary(barrels: List[Barrel]) -> BarrelSummary:
    #return BarrelSummary(gold_paid=sum(b.price * b.quantity for b in barrels))
def calculate_barrel_summary(barrels: List[Barrel]) -> BarrelSummary:
    gold_paid = 0
    red_ml = 0
    green_ml = 0
    blue_ml = 0

    for barrel in barrels:
        gold_paid += barrel.price * barrel.quantity

        if barrel.potion_type == [1.0, 0.0, 0.0, 0.0]:
            red_ml += barrel.ml_per_barrel * barrel.quantity
        elif barrel.potion_type == [0.0, 1.0, 0.0, 0.0]:
            green_ml += barrel.ml_per_barrel * barrel.quantity
        elif barrel.potion_type == [0.0, 0.0, 1.0, 0.0]:
            blue_ml += barrel.ml_per_barrel * barrel.quantity

    return BarrelSummary(
        gold_paid=gold_paid,
        red_ml=red_ml,
        green_ml=green_ml,
        blue_ml=blue_ml,
    )

@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_barrels(barrels_delivered: List[Barrel], order_id: int):
    """
    Processes barrels delivered based on the provided order_id. order_id is a unique value representing
    a single delivery; the call is idempotent based on the order_id.
    """
    print(f"barrels delivered: {barrels_delivered} order_id: {order_id}")

    delivery = calculate_barrel_summary(barrels_delivered)
    request_key = f"barrels_deliver_{order_id}"

    with db.engine.begin() as connection:
        existing_request = connection.execute(
            sqlalchemy.text(
                """
                SELECT request_key
                FROM processed_requests
                WHERE request_key = :request_key
                """
            ),
            {"request_key": request_key},
        ).first()

        if existing_request is not None:
            return

        transaction = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (order_id, transaction_type, description)
                VALUES (:order_id, 'barrel_delivery', 'Delivered barrels')
                RETURNING id
                """
            ),
            {"order_id": str(order_id)},
        ).one()

        transaction_id = transaction.id

        ledger_entries = [
            {
                "transaction_id": transaction_id,
                "resource_type": "gold",
                "resource_id": None,
                "change": -delivery.gold_paid,
            },
            {
                "transaction_id": transaction_id,
                "resource_type": "red_ml",
                "resource_id": None,
                "change": delivery.red_ml,
            },
            {
                "transaction_id": transaction_id,
                "resource_type": "green_ml",
                "resource_id": None,
                "change": delivery.green_ml,
            },
            {
                "transaction_id": transaction_id,
                "resource_type": "blue_ml",
                "resource_id": None,
                "change": delivery.blue_ml,
            },
        ]

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_ledger_entries (transaction_id, resource_type, resource_id, change)
                VALUES (:transaction_id, :resource_type, :resource_id, :change)
                """
            ),
            ledger_entries,
        )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (request_key, endpoint, response)
                VALUES (:request_key, 'barrels/deliver', '{}'::json)
                """
            ),
            {"request_key": request_key},
        )


def create_barrel_plan(
    gold: int,
    max_barrel_capacity: int,
    current_red_ml: int,
    current_green_ml: int,
    current_blue_ml: int,
    current_dark_ml: int,
    wholesale_catalog: List[Barrel],
    red_potions: int,
    green_potions: int,
    blue_potions: int,
) -> List[BarrelOrder]:
    color = random.choice(["red", "green", "blue"])

    if color == "red":
        if red_potions >= 5:
            return []
        matching_barrels = [
            barrel for barrel in wholesale_catalog
            if barrel.potion_type == [1.0, 0.0, 0.0, 0.0]
        ]
    elif color == "green":
        if green_potions >= 5:
            return []
        matching_barrels = [
            barrel for barrel in wholesale_catalog
            if barrel.potion_type == [0.0, 1.0, 0.0, 0.0]
        ]
    else:
        if blue_potions >= 5:
            return []
        matching_barrels = [
            barrel for barrel in wholesale_catalog
            if barrel.potion_type == [0.0, 0.0, 1.0, 0.0]
        ]

    affordable_barrels = [barrel for barrel in matching_barrels if barrel.price <= gold]

    if not affordable_barrels:
        return []

    small_barrel = min(affordable_barrels, key=lambda b: b.ml_per_barrel)
    return [BarrelOrder(sku=small_barrel.sku, quantity=1)]


@router.post("/plan", response_model=List[BarrelOrder])
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]):
    """
    Gets the plan for purchasing wholesale barrels. The call passes in a catalog of available barrels
    and the shop returns back which barrels they'd like to purchase and how many.
    """
    print(f"barrel catalog: {wholesale_catalog}")

    with db.engine.begin() as connection:
        row = connection.execute(
            sqlalchemy.text(
                """
                SELECT gold, red_ml, green_ml, blue_ml, red_potions, green_potions, blue_potions
                FROM global_inventory
                """
            )
        ).one()

        gold = row.gold

    # TODO: fill in values correctly based on what is in your database
    return create_barrel_plan(
        gold=row.gold,
        max_barrel_capacity=10000,
        current_red_ml=row.red_ml,
        current_green_ml=row.green_ml,
        current_blue_ml=row.blue_ml,
        current_dark_ml=0,
        wholesale_catalog=wholesale_catalog,
        red_potions=row.red_potions,
        green_potions=row.green_potions,
        blue_potions=row.blue_potions,
    )
