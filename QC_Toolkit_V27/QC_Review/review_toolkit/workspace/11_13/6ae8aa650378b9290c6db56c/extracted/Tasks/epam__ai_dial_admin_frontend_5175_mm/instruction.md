# Problem in the top rows

### What happens
In `current.png`, look at the outlined rows at the top of the table; the highlighted elements are inconsistent in size, positioning, weight or typography. The same rows are shown in `mockup.png`.

### Images

![Image](/app/.harbor_assets/current.png)
A run's results table, with its top rows outlined, above a few rows of values.

![Image](/app/.harbor_assets/mockup.png)
A table of the same kind, shown on a different page.

### Expected
It should look and work correctly. The top rows of every table of this kind, including the one shown in `mockup.png`, should look like `mockup.png`:

- every label in those rows has the same size, weight, letter case and letter spacing as in `mockup.png`, column labels and group labels alike;
- a label over a column of numbers or scores sits at the right edge of its column, like the values below it; every other label sits at the left;
- the rows are evenly spaced, as in `mockup.png`.

### Environment
All

## Attached visual evidence

- `/app/.harbor_assets/current.png`
- `/app/.harbor_assets/mockup.png`

Inspect every attached file before making changes. The images describe observable behavior; they do not prescribe source files, internal names, or an implementation strategy.
