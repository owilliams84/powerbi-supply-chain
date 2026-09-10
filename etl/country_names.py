"""English names for the destination countries, which the source writes in Spanish.

"Estados Unidos", "Alemania", "Reino Unido": a map fed the raw column geocodes some of them and
silently drops the rest. The ETL maps every name through this table and fails on any it does not
know, so a new country in a later extract cannot slip through untranslated.
"""

# Spanish name -> English name, for every name that differs.
SPANISH = {
    "Afganistán": "Afghanistan", "Alemania": "Germany", "Arabia Saudí": "Saudi Arabia",
    "Argelia": "Algeria", "Azerbaiyán": "Azerbaijan", "Bangladés": "Bangladesh",
    "Baréin": "Bahrain", "Belice": "Belize", "Benín": "Benin", "Bielorrusia": "Belarus",
    "Bosnia y Herzegovina": "Bosnia and Herzegovina", "Botsuana": "Botswana", "Brasil": "Brazil",
    "Bután": "Bhutan", "Bélgica": "Belgium", "Camboya": "Cambodia", "Camerún": "Cameroon",
    "Chipre": "Cyprus", "Corea del Sur": "South Korea", "Costa de Marfil": "Côte d'Ivoire",
    "Croacia": "Croatia", "Dinamarca": "Denmark", "Egipto": "Egypt",
    "Emiratos Árabes Unidos": "United Arab Emirates", "Eslovaquia": "Slovakia",
    "Eslovenia": "Slovenia", "España": "Spain", "Estados Unidos": "United States",
    "EE. UU.": "United States", "Etiopía": "Ethiopia", "Filipinas": "Philippines",
    "Finlandia": "Finland", "Francia": "France", "Gabón": "Gabon", "Grecia": "Greece",
    "Guadalupe": "Guadeloupe", "Guayana Francesa": "French Guiana",
    "Guinea Ecuatorial": "Equatorial Guinea", "Haití": "Haiti", "Hungría": "Hungary",
    "Irak": "Iraq", "Irlanda": "Ireland", "Irán": "Iran", "Italia": "Italy", "Japón": "Japan",
    "Jordania": "Jordan", "Kazajistán": "Kazakhstan", "Kenia": "Kenya",
    "Kirguistán": "Kyrgyzstan", "Lesoto": "Lesotho", "Libia": "Libya", "Lituania": "Lithuania",
    "Luxemburgo": "Luxembourg", "Líbano": "Lebanon", "Macedonia": "North Macedonia",
    "Malasia": "Malaysia", "Marruecos": "Morocco", "Martinica": "Martinique",
    "Moldavia": "Moldova", "Myanmar (Birmania)": "Myanmar", "México": "Mexico",
    "Noruega": "Norway", "Nueva Zelanda": "New Zealand", "Níger": "Niger", "Omán": "Oman",
    "Pakistán": "Pakistan", "Panamá": "Panama", "Papúa Nueva Guinea": "Papua New Guinea",
    "Países Bajos": "Netherlands", "Perú": "Peru", "Polonia": "Poland",
    "Reino Unido": "United Kingdom", "República Centroafricana": "Central African Republic",
    "República Checa": "Czech Republic",
    "República Democrática del Congo": "Democratic Republic of the Congo",
    "República Dominicana": "Dominican Republic", "República de Gambia": "Gambia",
    "República del Congo": "Republic of the Congo", "Ruanda": "Rwanda", "Rumania": "Romania",
    "Rusia": "Russia", "Sierra Leona": "Sierra Leone", "Singapur": "Singapore", "Siria": "Syria",
    "Suazilandia": "Eswatini", "SudAfrica": "South Africa", "Sudán": "Sudan",
    "Sudán del Sur": "South Sudan", "Suecia": "Sweden", "Suiza": "Switzerland",
    "Surinam": "Suriname", "Sáhara Occidental": "Western Sahara", "Tailandia": "Thailand",
    "Taiwán": "Taiwan", "Tayikistán": "Tajikistan", "Trinidad y Tobago": "Trinidad and Tobago",
    "Turkmenistán": "Turkmenistan", "Turquía": "Turkey", "Túnez": "Tunisia",
    "Ucrania": "Ukraine", "Uzbekistán": "Uzbekistan", "Yibuti": "Djibouti",
    "Zimbabue": "Zimbabwe",
}

# Names the source already writes the English way.
SAME = {
    "Albania", "Angola", "Argentina", "Armenia", "Australia", "Austria", "Barbados", "Bolivia",
    "Bulgaria", "Burkina Faso", "Burundi", "Canada", "Chad", "Chile", "China", "Colombia",
    "Costa Rica", "Cuba", "Ecuador", "El Salvador", "Eritrea", "Estonia", "Georgia", "Ghana",
    "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Honduras", "Hong Kong", "India",
    "Indonesia", "Israel", "Jamaica", "Kuwait", "Laos", "Liberia", "Madagascar", "Mali",
    "Mauritania", "Mongolia", "Montenegro", "Mozambique", "Namibia", "Nepal", "Nicaragua",
    "Nigeria", "Paraguay", "Portugal", "Puerto Rico", "Qatar", "Senegal", "Serbia", "Somalia",
    "Sri Lanka", "Tanzania", "Togo", "Uganda", "Uruguay", "Venezuela", "Vietnam", "Yemen",
    "Zambia",
}


def english(name: str) -> str:
    if name in SPANISH:
        return SPANISH[name]
    if name in SAME:
        return name
    raise KeyError(f"no English name for country {name!r} - add it to etl/country_names.py")
