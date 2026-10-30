"""
Design pseudocode only; no database or matching implementation yet.
These definitions can move into separate modules when implemented.

class Dispense
- fields:
    - color : string
    - duration_seconds : positive number
    - source : optional string identifying the source tank/material
- functions:
    - constructor : creates one dispense with valid color and duration

class Recipe
- fields:
    - id : globally unique recipe identifier across both collections
    - collection : INTENDED or UNMATCHED
    - dispenses : ordered list of Dispense objects
        - list position defines dispense order
        - dispense_count is a read-only property derived from list length
    - final_color : optional string, distinct from each dispense's color
- functions:
    - constructor : creates one complete recipe, not a collection
    - validate : checks identifier, collection, and dispense values
        - completed recipes must contain at least one dispense
- notes:
    - INTENDED means an accepted reference recipe
    - UNMATCHED means a known observed pattern outside the intended recipes
    - matching an UNMATCHED recipe never makes a vial pass verification
    - a recipe does not contain a per-vial match boolean or similarity score
    - reusing a recipe must not overwrite its reference measurements
    - metadata can be read directly from a retrieved Recipe object

class VialObservation
- fields:
    - run_id : identifier for the production run
    - vial_id : identifier for the vial within the run
    - dispenses : ordered list of observed Dispense objects
    - final_color : optional string
    - filling_complete : boolean
- notes:
    - workflow code builds this observation while the vial fills
    - preserve the actual measurements for each vial separately from recipes
    - incomplete or insufficient observations must not create new recipes

class RecipeRepository
- fields:
    - intended_recipes_by_id : map of identifiers to INTENDED Recipe objects
    - unmatched_recipes_by_id : map of identifiers to UNMATCHED Recipe objects
        - initially use in-memory storage; database operations will come later
- functions:
    - constructor : initializes access to both collections
    - add_recipe(recipe) : validates and stores in the specified collection
        - reject duplicate identifiers across both collections
        - collection field must agree with storage collection
    - get_recipe(recipe_id) : retrieves a recipe from either collection
        - returns no result if absent
    - list_recipes(collection) : returns recipes from the specified collection
    - update_recipe(recipe) : validates and updates an existing recipe
        - reject unknown identifiers and implicit collection changes
    - promote_to_intended(recipe_id, changed_by, reason) : returns updated Recipe
        - require an existing UNMATCHED recipe and valid recipe metadata
        - atomically remove from unmatched and insert into intended
        - set collection = INTENDED; preserve identifier and reference metadata
        - save a RecipeCollectionChange in the same operation
    - demote_to_unmatched(recipe_id, changed_by, reason) : returns updated Recipe
        - require an existing INTENDED recipe
        - atomically remove from intended and insert into unmatched
        - set collection = UNMATCHED; preserve identifier and reference metadata
        - save a RecipeCollectionChange in the same operation
    - list_collection_changes(recipe_id) : returns chronological change history
- notes:
    - handles storage access, not inference, vial tracking, or matching
    - unmatched recipes stay separate from intended reference recipes
    - automatic learning may add UNMATCHED recipes only
    - adding/changing intended recipes is an explicit reference-management action
    - identifier allocation will be defined with the database design
    - recipes belong to exactly one collection at a time
    - failed moves leave both collections and history unchanged
    - unknown identifiers return a not-found error
    - repeated moves to the current collection return the existing recipe
      without creating another history entry
    - serialize collection moves with inspection matching/storage initially
      so a concurrent move cannot produce an inconsistent classification

class RecipeCollectionChange
- fields:
    - change_id : unique identifier for this change
    - recipe_id : unchanged recipe identifier
    - previous_collection : INTENDED or UNMATCHED
    - new_collection : INTENDED or UNMATCHED
    - changed_by : identity of the user making the change
    - changed_at : timestamp
    - reason : explanation of approval or removal from the intended set
- notes:
    - history is retained separately from the recipe's current collection

class FieldDifference
- fields:
    - field : metadata path, such as dispenses[1].color or dispense_count
    - dispense_number : optional human-readable, one-based dispense number
    - expected : value from the compared recipe, or none if absent
    - observed : value from the vial observation, or none if absent
    - tolerance : optional allowed deviation, including units where relevant
    - reason : explanation of the difference
- notes:
    - report extra/missing dispenses as well as differing field values

class MatchResult
- fields:
    - compared_collection : INTENDED or UNMATCHED
    - candidate_recipe_id : best comparable recipe, or none if no candidate
    - similarity_score : number from 0 to 1, or none if not comparable
    - meets_threshold : boolean
    - status : MATCH, NO_MATCH, or INSUFFICIENT_DATA
    - differences : list of FieldDifference objects for the candidate recipe
    - reasons : list of explanations for the result
    - method_version : version of scoring rules and tolerances
    - threshold_used : threshold applied to this comparison
- notes:
    - retain the closest intended candidate and differences even on NO_MATCH
    - the score measures recipe similarity, not model confidence
    - empty collection returns NO_MATCH with no candidate or score
    - insufficient observation data returns INSUFFICIENT_DATA

class RecipeMatcher
- fields:
    - intended_threshold : configurable number from 0 to 1 (proposal: 0.90)
    - unmatched_threshold : separately configurable reuse threshold
- functions:
    - find_best_match(observation, recipes, collection) : returns MatchResult
        - require complete, sufficient observation data
        - require supplied recipes to belong to the specified collection
        - compare dispense count, order, colors, and durations
        - include final color/source only if scoring rules define their use
        - select the highest-scoring comparable recipe
        - use score >= the collection's threshold for a match
        - report NO_MATCH if no candidate meets that threshold
        - return field differences against the best comparable candidate
        - report INSUFFICIENT_DATA if a reliable comparison cannot be made
- decisions needed before implementation:
    - color representation, duration tolerances, and feature weights
    - handling unequal dispense counts and missing optional values
    - whether source tank/material participates in matching
    - unmatched reuse threshold and handling tied/ambiguous best matches
- notes:
    - compares against one collection at a time
    - does not save recipes or modify observations

class VialInspection
- fields:
    - inspection_id : unique identifier for this inspection
    - observation : snapshot of the vial's actual VialObservation
    - recipe_id : linked intended/unmatched recipe, or none if unresolved
    - recipe_collection : collection AT INSPECTION TIME, or none if unresolved
    - verification_status : PASS, FAIL, or INSUFFICIENT_DATA
    - intended_comparison : MatchResult from the intended search
    - unmatched_comparison : MatchResult from the unmatched search, or none
    - created_new_recipe : boolean
    - inspected_at : timestamp
- notes:
    - each completed vial gets an inspection, even when a recipe is reused
    - an UNMATCHED classification at inspection time means FAIL against
      intended recipes, even if that recipe is promoted later
    - collection moves must not rewrite previous inspection results,
      comparison details, or collection-at-inspection values
    - UI may display the recipe's current collection separately from its
      historical inspection classification
    - a newly created unmatched recipe has no measured similarity to an existing
      unmatched candidate; retain the original NO_MATCH comparison
    - intended_comparison supplies the UI's intended-recipe field differences
    - FAIL means outside the intended set, not proof of a physical filling defect

class InspectionRepository
- functions:
    - save_inspection(inspection) : saves one vial's measurements and results
    - get_inspection(inspection_id) : retrieves one inspection
    - list_inspections_for_recipe(recipe_id) : retrieves linked occurrences
- notes:
    - occurrence counts come from linked inspections, not duplicate recipes
    - recipe and inspection writes should commit together when using a database

Recipe-management workflow (outside the repository and matcher)
- frontend offers "Approve as intended recipe" for an unmatched recipe
  and "Move to unmatched" for an intended recipe
- backend validates the requested action and user permission
- derive changed_by from the authenticated user, not a frontend identity field
- call the explicit promotion/demotion repository operation with a reason
- return the updated recipe and refresh the frontend collections
- promotion means future matching can pass against this intended recipe
- demotion means that recipe is no longer an accepted intended reference
    - a future vial may still pass against a DIFFERENT intended recipe
- preserve previous inspections; collection changes do not reclassify history
- automatic matching must never promote a recipe

Vial-inspection workflow (outside the repositories and matcher)
- finish collecting and validate the vial observation
- compare against ALL intended recipes first
    - MATCH:
        - link the inspection to that existing INTENDED recipe
        - verification_status = PASS; do not search unmatched recipes
    - INSUFFICIENT_DATA:
        - retain the inspection for review/reprocessing; do not create a recipe
    - NO_MATCH with sufficient observation data:
        - preserve the closest intended candidate, score, and field differences
        - compare against the UNMATCHED recipe collection
            - MATCH:
                - link to the existing UNMATCHED recipe; create no new recipe
                - verification_status = FAIL
            - NO_MATCH:
                - create a Recipe from a copy of the observed dispense sequence
                - allocate a unique identifier; set collection = UNMATCHED
                - store it and link this inspection to the new recipe
                - verification_status = FAIL; created_new_recipe = true
            - INSUFFICIENT_DATA:
                - retain intended NO_MATCH evidence; do not create a recipe
                - verification_status = INSUFFICIENT_DATA; leave link unresolved
- persist the inspection, including both comparison results when available
- do not modify a recipe's reference measurements when linking another vial
- serialize unmatched lookup/create initially; a database implementation must
  prevent concurrent inspections from creating duplicate unmatched patterns
- retrying the same inspection must not create duplicate recipes/occurrences
"""
