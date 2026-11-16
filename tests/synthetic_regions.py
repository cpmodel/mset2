from openpyxl import load_workbook


REGION_RENAMES = {
    "AFR": "GONT",
    "MEN": "HAVNOR",
    "LAC": "ROKE",
    "NAM": "OSSKIL",
    "EAS": "KARGAD",
    "SAS": "GONDOR",
    "SEP": "ROHAN",
    "EUR": "MORDOR",
    "AJN": "SHIRE",
    "EEA": "RIVENDELL",
}

REGION_COLUMNS = {
    "REG_imp",
    "REG_exp",
    "Agg_region",
    "target-country-iso3",
    "origin-country-iso3",
}


def rename_frame_regions(frame):
    for column in REGION_COLUMNS.intersection(frame.columns):
        frame[column] = frame[column].replace(REGION_RENAMES)

    if hasattr(frame.index, "set_levels"):
        for level, name in enumerate(frame.index.names):
            if name in REGION_COLUMNS:
                frame.index = frame.index.set_levels(
                    frame.index.levels[level].map(lambda value: REGION_RENAMES.get(value, value)),
                    level=level,
                )
    elif frame.index.name in REGION_COLUMNS:
        frame.index = frame.index.map(lambda value: REGION_RENAMES.get(value, value))
    return frame


def rename_region_lookup(path):
    workbook = load_workbook(path)
    sheet = workbook["R"]
    columns = {cell.value: cell.column for cell in sheet[1]}
    acronym_column = columns["Region_acronyms"]
    name_column = columns["Region_names"]
    for row in range(2, sheet.max_row + 1):
        region = sheet.cell(row, acronym_column).value
        if region in REGION_RENAMES:
            renamed = REGION_RENAMES[region]
            sheet.cell(row, acronym_column).value = renamed
            sheet.cell(row, name_column).value = renamed
    workbook.save(path)

