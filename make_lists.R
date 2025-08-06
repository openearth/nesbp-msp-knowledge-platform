require(tidyverse)
require(DBI)

update_csv_files <- FALSE


conditionalWrite <- function(condition = update_csv_files, object, path){
  if(condition){
    write_csv2(object, path)
    cat(substitute(object), "is written to", path)
  } else
    cat("nothing is written to", path)
}



# create in-memory database
# Should be replaced by file database

# con <- dbConnect(RSQLite::SQLite(), ":memory:")

con <- dbConnect(RSQLite::SQLite(), "data/gnsbi_platform.db")

# construct lists



user_profile <- tribble(
  ~name, ~code, ~dikw,
  'Policy makers', 'PM', 'IK',
  'MSP Experts', 'Ex', 'DIK',
  'Industry', 'In', 'DIK',
  'General public', 'GP', 'IK'
)

conditionalWrite(update_csv_files, user_profile, "data/user_profile.csv")
dbWriteTable(con, "user_profile", user_profile)




information_entry <- tribble(
  ~name, ~code, ~explanation,
  'input data', 'input', 'MSP underlying maps used for zoning.',
  'knowledge base', 'knowledge', 'Background knowledge used for national zoning and international coordination of MSP.',
  'msp zoning', 'zoning', 'Outcome of MSP process as zoning areas.'
)

conditionalWrite(update_csv_files, information_entry, "data/information_entry.csv")
dbWriteTable(con, "information_entry", information_entry)



knowledge_category <- tribble(
  ~name, ~code,
  'Who is who', 'who',
  'MSP evolution	Priorities/opportunities for cooperation', 'opportunities',
  'Climate Change',	'climate',
  'Nature conservation', 'nature',
  'resource management', 'resources',
  'data resources / INPUT DATA', 'data',
  'legislation', 'leg'
  # new activities
)

conditionalWrite(update_csv_files, knowledge_category, "data/knowledge_category.csv")
dbWriteTable(con, "knowledge_category", knowledge_category)



knowledge_sub_category <- tribble(
  # headers
  ~name, 
  ~code,
  ~explanation,
  ~knowledge_category_code,
  # content
  "Bird conservation", 
  "birds", 
  "Knowledge about the occurrence of birds e.g. depending on the time of year.",
  "climate"
)

conditionalWrite(update_csv_files, knowledge_sub_category, "data/knowledge_sub_category.csv")
dbWriteTable(con, "knowledge_sub_category", knowledge_sub_category)

  

country <- read_csv2("data/countries.csv")
dbWriteTable(con, "country", country)



owner <- country %>%
  select(name = country.name.en,
         code = iso2c
          ) %>%
  bind_rows(
    tribble(
      ~name, ~code,
      'OSPAR', 'ospar',
      'EMODnet', 'emodnet',
      'ICES', 'ices',
      'GNSBI', 'gnsbi',
      'HELCOM', 'helcom'
    )
  )

conditionalWrite(update_csv_files, owner, "data/owner.csv")
dbWriteTable(con, "owner", owner)



questions <- tribble(
  ~name, ~code, ~explanation,
  "What is the tension between nature and offshore wind farms", 
  "tension_nature_owf", 
  "Explanation in short."
)

conditionalWrite(update_csv_files, owner, "data/questions.csv")
dbWriteTable(con, "questions", questions)





main_table <- tribble(
  ~question, ~user_profile, ~knowledge_category, ~information_entry, ~owner, ~maplink, ~documentlink,
  "tension_nature_owf", 
  "PM", 
  "nature", 
  "knowledge", 
  "gnsbi", 
  "https://viewer.openearth.nl/compendium-greater-north-sea/?folders=143750791,143750761,146750132,146750025,146743026,146742883&layers=168934194,146743135,146750044,146750152,143750774&layerNames=Common%20Database%20of%20Designated%20Areas%20-%20CDDA%20%28INSPIRE%29,Protected%20Sites%20%28INSPIRE%29.,Marine%20Conservation%20Zones%20%28JNCC%29.,Scottish%20Marine%20Protected%20Areas%20%28JNCC%29.,OSPAR%20MPA%202023%20%28OSPAR%29",
  "https://testsysteemrapportage.nl/compendium-greater-north-sea/food_and_fishing.html"
)

conditionalWrite(update_csv_files, main_table, "data/main_table.csv")
dbWriteTable(con, "main_table", main_table)


# close connection (database disappears from memory)
DBI::dbDisconnect(con)


#==== test =======

con <- dbConnect(RSQLite::SQLite(), "data/gnsbi_platform.db")

# list all tables and read one
dbListTables(con)
dbReadTable(con, "country")

# with dbplyr, tables can be treated as in memory dataframes
require(dbplyr)
country %>% arrange() %>% collect()
main_table %>% 
  left_join(questions, by = c(question = "code")) %>% 
  left_join(user_profile, by = c(user_profile = "code")) %>%
  collect()


DBI::dbDisconnect(con)
