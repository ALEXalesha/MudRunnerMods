# Uploading to the Steam Workshop

MudRunner Workshop items are published only from the MudRunner Editor (Steam > Library > Tools > "Spintires: MudRunner - Editor"). Nothing in this repository uploads anything.

Build the folders first:

```
.venv\Scripts\python tools\build_workshop.py
```

`workshop\` then holds seven folders, numbered in the load order:

| Folder | Title to type | Adds |
|---|---|---|
| 01_OpenTrail_Hyper_Power | OpenTrail Hyper Power | 20 trucks "(Hyper)" |
| 02_OpenTrail_Powerful_Engines | OpenTrail Powerful Engines | 20 trucks "(Powerful)" |
| 03_OpenTrail_AWD_and_Diff_Lock | OpenTrail AWD and Diff Lock | 5 trucks "(AWD)" |
| 04_OpenTrail_Deep_Fording | OpenTrail Deep Fording | 20 trucks "(Deep Fording)" |
| 05_OpenTrail_No_Damage | OpenTrail No Damage | 20 trucks "(No Damage)" |
| 06_OpenTrail_Infinite_Fuel | OpenTrail Infinite Fuel | 20 trucks "(Infinite Fuel)" |
| 07_OpenTrail_Grippy_Wheels | OpenTrail Grippy Wheels | 24 wheel types and 20 trucks "(Grippy)" |

Each folder:

| File | Use |
|---|---|
| `mod\` | Copy its CONTENTS into the Editor's new mod folder |
| `mod\strings.xml` | Truck names (English: the Editor has no mod localization) |
| `mod\classes\trucks\*.xml` | New trucks: full copies of the stock trucks (no `<_parent>`) with the change |
| `mod\billboards\trucks\*.dds` | Truck-selection icons of the new trucks (copies of the stock icons) |
| `mod\classes\wheels\*.xml` | Grippy Wheels only |
| `mod\preview.png` | 512x512 preview |
| `steam_page.txt` | Title, visibility, change note and description, CRLF |
| `steam_description.txt` | The description only, CRLF, to copy whole |

## Steps (per mod)

1. Start the Editor with Steam running. First time: Settings > Paths, pick the game folder, press "Install Game Media".
2. File View > right click `_mods` > Create new mod. A folder with an 8 to 16 character id appears in `Media\_mods\`.
3. Copy the contents of `workshop\NN_...\mod\` into that folder (`strings.xml`, `classes\`, `billboards\`, `preview.png`).
4. Optional test: start the game, Proving Ground > Spawn: unpublished mods are available there.
5. Right click the mod > Publish. Fill in from `steam_page.txt`: Title, Description (paste `steam_description.txt`), Visibility (Private for the first upload), change note "Version 1.0.0". Keep `preview.png` or press Autogenerate.
6. First upload only: accept the Workshop terms via the link in the dialog.
7. Publish, then subscribe to the item on the Workshop page.

## Rules and known messages

- Only `.xml` and `.png` are in `mod\`: files with other extensions give an "unrecognized file extension" warning and are left out.
- File names are lowercase letters, digits and `_`, unique across all mods (the game ignores folders). Each mod has its own prefix: `oth_`, `otp_`, `ota_`, `otw_`, `otd_`, `otf_`, `otg_`.
- The preview cannot be changed on the Workshop page; edit `preview.png` and publish again.
- After an update, players may need to unsubscribe and subscribe again.
- The description box is a plain Windows edit field: the copy-paste files use CRLF so line breaks survive.
