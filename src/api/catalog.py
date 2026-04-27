from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Annotated

import sqlalchemy
from src import database as db

router = APIRouter()


class CatalogItem(BaseModel):
    sku: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{1,20}$")]
    name: str
    quantity: Annotated[int, Field(ge=1, le=10000)]
    price: Annotated[int, Field(ge=1, le=500)]
    potion_type: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Must contain exactly 4 elements: [r, g, b, d]",
    )


# Placeholder function, you will replace this with a database call
#def create_catalog() -> List[CatalogItem]:
#    return [
#        CatalogItem(
#            sku="RED_POTION_0",
#            name="red potion",
#            quantity=1,
 #           price=50,
##            potion_type=[100, 0, 0, 0],
#        )
#    ]

def create_catalog() -> List[CatalogItem]:
    with db.engine.begin() as connection:
        rows = connection.execute(
            sqlalchemy.text(
                """
                SELECT
                    p.id,
                    p.sku,
                    p.name,
                    p.price,
                    p.red,
                    p.green,
                    p.blue,
                    p.dark,
                    COALESCE(SUM(l.change), 0) AS quantity
                FROM potions p
                LEFT JOIN inventory_ledger_entries l
                    ON l.resource_type = 'potion'
                    AND l.resource_id = p.id
                GROUP BY p.id, p.sku, p.name, p.price, p.red, p.green, p.blue, p.dark
                HAVING COALESCE(SUM(l.change), 0) > 0
                """
            )
        ).mappings().all()

    catalog = []

    for row in rows:
        catalog.append(
            CatalogItem(
                sku=row["sku"],
                name=row["name"],
                quantity=row["quantity"],
                price=row["price"],
                potion_type=[row["red"], row["green"], row["blue"], row["dark"]],
            )
        )

    return catalog

@router.get("/catalog/", tags=["catalog"], response_model=List[CatalogItem])
def get_catalog() -> List[CatalogItem]:
    """
    Retrieves the catalog of items. Each unique item combination should have only a single price.
    You can have at most 6 potion SKUs offered in your catalog at one time.
    """
    return create_catalog()
