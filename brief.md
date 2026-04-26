## Project Brief

This project is to create a recipe scraper that will create a database of structured recipes to power a semantic search tool for open webui.

The expected flow is

1. Select sites to scrape from (env var is fine here, dont need ui)

2. Start a run to find all recipes on those sites

3. Add recipe urls to a database with status = discovered (not processed)

4. Once all recipes from all sites are discovered, start working through that queue with a scraper worker

5. The scraper worker picks up the next discovered url, sets its status to processing

6. It opens a playwright browser to open the recipe page and save the html content

7. It runs html content through [GitHub - hhursev/recipe-scrapers: Python package for scraping recipes data · GitHub](https://github.com/hhursev/recipe-scrapers) to get the strucured recipe

8. Store structured recipe in database and sets the status to complete

9. Once the job is complete, index the recipe metadata with mellisearch or similar

10. The open webui tool is responsible for using mellisearch api to find recipes to show to users, when users want to see the recipe it renders the structured recipe from the database in a nice markdown format

11. Users can also favorite recipes and ask for favorites with the open webui tool

### Problem Statement

Our family loves recipes, but it's a pain to go through the individual sites and use a search engine to find new ones. We'd prefer to use the open webui instance that we use for other general queries in our home.

### Goals

- Create our own curated recipe database from the sites we love the most

- This should be as portable as possible, ideally in a single docker container
