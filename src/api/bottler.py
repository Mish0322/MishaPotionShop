from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from typing import List
from src.api import auth

from src import database as db
import sqlalchemy

router = APIRouter(
    prefix="/bottler",
    tags=["bottler"],
    dependencies=[Depends(auth.get_api_key)],
)


class PotionMixes(BaseModel):
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )
    quantity: int = Field(
        ..., ge=1, le=10000, description="Quantity must be between 1 and 10,000"
    )

    @field_validator("potion_type")
    @classmethod
    def validate_potion_type(cls, potion_type: List[int]) -> List[int]:
        if sum(potion_type) != 100:
            raise ValueError("Sum of potion_type values must be exactly 100")
        return potion_type


@router.post("/deliver/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_deliver_bottles(potions_delivered: List[PotionMixes], order_id: int):
    """
    Delivery of potions requested after plan. order_id is a unique value representing
    a single delivery; the call is idempotent based on the order_id.
    """
    print(f"potions delivered: {potions_delivered} order_id: {order_id}")

    request_key = f"bottler_deliver_{order_id}"

    with db.engine.begin() as connection:
        already_done = connection.execute(
            sqlalchemy.text(
                """
                SELECT request_key FROM processed_requests
                WHERE request_key = :request_key
                """
            ),
            {"request_key": request_key},
        ).first()

        if already_done:
            return

        transaction = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO inventory_transactions (order_id, transaction_type, description)
                VALUES (:order_id, 'bottler_delivery', 'Delivered bottled potions')
                RETURNING id
                """
            ),
            {"order_id": str(order_id)},
        ).one()

        for potion in potions_delivered:
            red_used = potion.quantity * potion.potion_type[0] // 100
            green_used = potion.quantity * potion.potion_type[1] // 100
            blue_used = potion.quantity * potion.potion_type[2] // 100

            potion_row = connection.execute(
                sqlalchemy.text(
                    """
                    SELECT id FROM potions
                    WHERE red = :red AND green = :green AND blue = :blue AND dark = :dark
                    """
                ),
                {
                    "red": potion.potion_type[0],
                    "green": potion.potion_type[1],
                    "blue": potion.potion_type[2],
                    "dark": potion.potion_type[3],
                },
            ).first()

            if potion_row is None:
                continue

            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO inventory_ledger_entries
                    (transaction_id, resource_type, resource_id, change)
                    VALUES
                    (:transaction_id, 'red_ml', NULL, :red_change),
                    (:transaction_id, 'green_ml', NULL, :green_change),
                    (:transaction_id, 'blue_ml', NULL, :blue_change),
                    (:transaction_id, 'potion', :potion_id, :potion_change)
                    """
                ),
                {
                    "transaction_id": transaction.id,
                    "red_change": -red_used,
                    "green_change": -green_used,
                    "blue_change": -blue_used,
                    "potion_id": potion_row.id,
                    "potion_change": potion.quantity,
                },
            )

        connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO processed_requests (request_key, endpoint, response)
                VALUES (:request_key, 'bottler/deliver', '{}'::json)
                """
            ),
            {"request_key": request_key},
        )


def create_bottle_plan(
    red_ml: int,
    green_ml: int,
    blue_ml: int,
    dark_ml: int,
    maximum_potion_capacity: int,
    current_potion_inventory: List[PotionMixes],
) -> List[PotionMixes]:
    # TODO: Create a real bottle plan logic
    plan = []

    with db.engine.begin() as connection:
        potions = connection.execute(
            sqlalchemy.text(
                """
                SELECT red, green, blue, dark
                FROM potions
                """
            )
        ).mappings().all()

    for potion in potions:
        red = potion["red"]
        green = potion["green"]
        blue = potion["blue"]
        dark = potion["dark"]

        if dark != 0:
            continue

        possible_quantities = []

        if red > 0:
            possible_quantities.append(red_ml // red)
        if green > 0:
            possible_quantities.append(green_ml // green)
        if blue > 0:
            possible_quantities.append(blue_ml // blue)

        if not possible_quantities:
            continue

        quantity = min(possible_quantities)

        if quantity > 0:
            plan.append(
                PotionMixes(
                    potion_type=[red, green, blue, dark],
                    quantity=quantity,
                )
            )

    return plan


@router.post("/plan", response_model=List[PotionMixes])
def get_bottle_plan():
    """
    Gets the plan for bottling potions.
    Each bottle has a quantity of what proportion of red, green, blue, and dark potions to add.
    Colors are expressed in integers from 0 to 100 that must sum up to exactly 100.
    """
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN resource_type = 'red_ml' THEN change ELSE 0 END), 0) AS red_ml,
                    COALESCE(SUM(CASE WHEN resource_type = 'green_ml' THEN change ELSE 0 END), 0) AS green_ml,
                    COALESCE(SUM(CASE WHEN resource_type = 'blue_ml' THEN change ELSE 0 END), 0) AS blue_ml
                FROM inventory_ledger_entries
                """
            )
        ).mappings().first()

    return create_bottle_plan(
        red_ml=result["red_ml"],
        green_ml=result["green_ml"],
        blue_ml=result["blue_ml"],
        dark_ml=0,
        maximum_potion_capacity=50,
        current_potion_inventory=[],
    )

if __name__ == "__main__":
    print(get_bottle_plan())
