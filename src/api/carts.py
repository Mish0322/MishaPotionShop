from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import sqlalchemy
from src.api import auth
from enum import Enum
from typing import List, Optional
from src import database as db

router = APIRouter(
    prefix="/carts",
    tags=["cart"],
    dependencies=[Depends(auth.get_api_key)],
)


class SearchSortOptions(str, Enum):
    customer_name = "customer_name"
    item_sku = "item_sku"
    line_item_total = "line_item_total"
    timestamp = "timestamp"


class SearchSortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class LineItem(BaseModel):
    line_item_id: int
    item_sku: str
    customer_name: str
    line_item_total: int
    timestamp: str


class SearchResponse(BaseModel):
    previous: Optional[str] = None
    next: Optional[str] = None
    results: List[LineItem]


@router.get("/search/", response_model=SearchResponse, tags=["search"])
def search_orders(
    customer_name: str = "",
    potion_sku: str = "",
    search_page: str = "",
    sort_col: SearchSortOptions = SearchSortOptions.timestamp,
    sort_order: SearchSortOrder = SearchSortOrder.desc,
):
    """
    Search for cart line items by customer name and/or potion sku.
    """
    return SearchResponse(
        previous=None,
        next=None,
        results=[
            LineItem(
                line_item_id=1,
                item_sku="1 oblivion potion",
                customer_name="Scaramouche",
                line_item_total=50,
                timestamp="2021-01-01T00:00:00Z",
            )
        ],
    )


class Customer(BaseModel):
    customer_id: str
    customer_name: str
    character_class: str
    character_species: str
    level: int = Field(ge=1, le=20)


@router.post("/visits/{visit_id}", status_code=status.HTTP_204_NO_CONTENT)
def post_visits(visit_id: int, customers: List[Customer]):
    """
    Shares the customers that visited the store on that tick.
    """
    print(customers)
    pass


class CartCreateResponse(BaseModel):
    cart_id: int


@router.post("/", response_model=CartCreateResponse)
def create_cart(new_cart: Customer):
    """
    Creates a new cart for a specific customer.
    """
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                """
                INSERT INTO carts (customer_id, customer_name, character_class, character_species, level)
                VALUES (:customer_id, :customer_name, :character_class, :character_species, :level)
                RETURNING id
                """
            ),
            {
                "customer_id": new_cart.customer_id,
                "customer_name": new_cart.customer_name,
                "character_class": new_cart.character_class,
                "character_species": new_cart.character_species,
                "level": new_cart.level,
            },
        ).one()

    return CartCreateResponse(cart_id=result.id)


class CartItem(BaseModel):
    quantity: int = Field(ge=1, description="Quantity must be at least 1")


@router.post("/{cart_id}/items/{item_sku}", status_code=status.HTTP_204_NO_CONTENT)
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    print(
        f"cart_id: {cart_id}, item_sku: {item_sku}, cart_item: {cart_item}"
    )

    with db.engine.begin() as connection:
        cart = connection.execute(
            sqlalchemy.text(
                """
                SELECT id FROM carts
                WHERE id = :cart_id
                """
            ),
            {"cart_id": cart_id},
        ).first()

        if cart is None:
            raise HTTPException(status_code=404, detail="Cart not found")

        potion = connection.execute(
            sqlalchemy.text(
                """
                SELECT id FROM potions
                WHERE sku = :item_sku
                """
            ),
            {"item_sku": item_sku},
        ).first()

        if potion is None:
            raise HTTPException(status_code=404, detail="Potion not found")

        existing_item = connection.execute(
            sqlalchemy.text(
                """
                SELECT id FROM cart_items
                WHERE cart_id = :cart_id AND potion_id = :potion_id
                """
            ),
            {"cart_id": cart_id, "potion_id": potion.id},
        ).first()

        if existing_item is None:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO cart_items (cart_id, potion_id, quantity)
                    VALUES (:cart_id, :potion_id, :quantity)
                    """
                ),
                {
                    "cart_id": cart_id,
                    "potion_id": potion.id,
                    "quantity": cart_item.quantity,
                },
            )
        else:
            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE cart_items
                    SET quantity = :quantity
                    WHERE id = :cart_item_id
                    """
                ),
                {
                    "quantity": cart_item.quantity,
                    "cart_item_id": existing_item.id,
                },
            )

    return status.HTTP_204_NO_CONTENT


class CheckoutResponse(BaseModel):
    total_potions_bought: int
    total_gold_paid: int


class CartCheckout(BaseModel):
    payment: str


@router.post("/{cart_id}/checkout", response_model=CheckoutResponse)
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Handles the checkout process for a specific cart.
    """

    with db.engine.begin() as connection:
        cart = connection.execute(
            sqlalchemy.text(
                """
                SELECT id FROM carts
                WHERE id = :cart_id
                """
            ),
            {"cart_id": cart_id},
        ).first()

        if cart is None:
            raise HTTPException(status_code=404, detail="Cart not found")

        items = connection.execute(
            sqlalchemy.text(
                """
                SELECT ci.id, ci.quantity, p.id AS potion_id, p.price, p.inventory
                FROM cart_items ci
                JOIN potions p ON ci.potion_id = p.id
                WHERE ci.cart_id = :cart_id
                """
            ),
            {"cart_id": cart_id},
        ).mappings().all()

        total_potions_bought = 0
        total_gold_paid = 0

        for item in items:
            total_potions_bought += item["quantity"]
            total_gold_paid += item["quantity"] * item["price"]

            connection.execute(
                sqlalchemy.text(
                    """
                    UPDATE potions
                    SET inventory = inventory - :quantity
                    WHERE id = :potion_id
                    """
                ),
                {
                    "quantity": item["quantity"],
                    "potion_id": item["potion_id"],
                },
            )

        row = connection.execute(
            sqlalchemy.text(
                """
                SELECT gold FROM global_inventory
                """
            )
        ).one()

        new_gold = row.gold + total_gold_paid

        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory
                SET gold = :gold
                """
            ),
            {"gold": new_gold},
        )

    return CheckoutResponse(
        total_potions_bought=total_potions_bought,
        total_gold_paid=total_gold_paid,
    )