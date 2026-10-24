Create a new investigation case folder from templates.

Arguments: $ARGUMENTS (case name, e.g. "stolen-ip-acme" or "harassment-jane-doe")

## Steps

1. Ask the founder for:
   - Case name (short slug, used in folder name)
   - Brief description of the investigation
   - Client name (if applicable)
2. Generate a case ID: `case-NNN-{slug}` (increment from highest existing case number in `investigations/`)
3. Copy the template folder:
   ```
   cp -R templates/new-investigation investigations/case-NNN-{slug}
   ```
4. Update the scope.md template with the case description and today's date
5. Create the memory/sessions/ directory
6. Write the case folder name (e.g. `case-NNN-{slug}`, no path) as the only line of `.active-case`. Every `/q-*` command reads this file to find the case.
7. Confirm the new case folder to the founder
8. Suggest running `/q-scope` to fully define the investigation parameters
