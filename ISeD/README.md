# ISeD orodja (QGIS vtičnik)

ISeD orodja so neuradni vtičnik za QGIS, namenjen uporabnikom informacijskega sistema ISeD. Omogoča prenos GURS podatkov, urejanje geometrij, delo z ISeD sloji ter izvoz v standardne formate.

## Ključne zmožnosti
- Dialog in Dock vmesnik.
- Prenos parcel in stavb GURS prek WFS (EPSG:3794).
- Uvoz GURS WMS slojev prek GetCapabilities.
- Ustvarjanje praznega ISeD sloja z atributom `edit_type`.
- Orodja za združevanje, buffer, obrezovanje vplivnih območij.
- Urejanje geometrij (vertex tool, union, kopiranje geometrij).
- Nastavljanje simbologije prek `ised.qml` in `OPN_PNRP_OZN.qml`.
- Izvoz v Shapefile in ZIP.

## Namestitev
1. Kopiraj projekt v QGIS plugin mapo.
2. Zagotovi, da mapa `Resources/` vsebuje stile in ikone.
3. V QGIS omogoči vtičnik v *Manage and Install Plugins*.

## Uporaba
Po aktivaciji se prikaže meni in orodna vrstica *ISeD*. Prek dialoga ali zasidranega panela lahko:
- preneseš GURS sloje,
- urejaš ISeD sloje,
- uporabljaš napredna orodja,
- izvoziš podatke.

## Licenca
Dodaj licenco po želji (MIT, GPL ipd.).

