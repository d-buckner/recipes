from dataclasses import dataclass, field


SqlParam = str | int


SEARCH_RESULT_COLUMNS = """
       r.id, r.url, r.site,
       r.title AS title,
       json_extract(r.recipe_json, '$.description') AS description,
       r.total_time AS total_time,
       json_extract(r.recipe_json, '$.yields') AS yields,
       json_extract(r.recipe_json, '$.image') AS image,
       r.site_name AS site_name,
       r.author AS author,
       r.cuisine_json AS cuisine,
       r.category_json AS category,
       (r.thumbnail IS NOT NULL) AS has_thumbnail,
       CASE WHEN f.recipe_id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite,
       COALESCE(
         (SELECT GROUP_CONCAT(c.name, '||')
          FROM collection_recipes cr_names JOIN collections c ON c.id = cr_names.collection_id
          WHERE cr_names.recipe_id = r.id),
         ''
       ) AS collection_names
"""


def in_placeholders(values: list[str]) -> str:
    return "(" + ",".join("?" * len(values)) + ")"


@dataclass(frozen=True)
class RecipeFilters:
    author: list[str] = field(default_factory=list)
    cuisine: list[str] = field(default_factory=list)
    category: list[str] = field(default_factory=list)
    site: list[str] = field(default_factory=list)
    min_time: int | None = None
    max_time: int | None = None

    def to_sql(self, alias: str = "r") -> tuple[str, list[SqlParam]]:
        conditions: list[str] = []
        params: list[SqlParam] = []
        if self.author:
            conditions.append(f"{alias}.author IN {in_placeholders(self.author)}")
            params.extend(self.author)
        if self.cuisine:
            conditions.append(
                f"EXISTS (SELECT 1 FROM json_each({alias}.cuisine_json) "
                f"WHERE value IN {in_placeholders(self.cuisine)})"
            )
            params.extend(self.cuisine)
        if self.category:
            conditions.append(
                f"EXISTS (SELECT 1 FROM json_each({alias}.category_json) "
                f"WHERE value IN {in_placeholders(self.category)})"
            )
            params.extend(self.category)
        if self.site:
            conditions.append(f"{alias}.site IN {in_placeholders(self.site)}")
            params.extend(self.site)
        if self.min_time is not None or self.max_time is not None:
            conditions.append(f"{alias}.total_time IS NOT NULL")
        if self.min_time is not None:
            conditions.append(f"{alias}.total_time >= ?")
            params.append(self.min_time)
        if self.max_time is not None:
            conditions.append(f"{alias}.total_time <= ?")
            params.append(self.max_time)
        if not conditions:
            return "", params
        return " AND " + " AND ".join(conditions), params
