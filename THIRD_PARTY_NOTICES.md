# Third-Party Notices

This project source code is licensed under `0BSD` (see `LICENSE`).

The project depends on third-party Python packages, each under its own license.
When redistributing builds/bundles that include these packages, keep this notice
and include the corresponding third-party license texts.

Bundled license text files are provided under `third_party_licenses/`.

## Runtime dependency licenses

Source for this list:
- `requirements.txt`
- Installed package metadata for current runtime resolution

Runtime set resolved from current requirements:

| Package | Version | License |
|---|---:|---|
| customtkinter | 5.2.2 | CC0-1.0 (metadata), with MIT license classifier |
| darkdetect | 0.8.0 | BSD-3-Clause |
| stashapp-tools | 0.2.59 | MIT |
| requests | 2.32.5 | Apache-2.0 |
| certifi | 2025.11.12 | MPL-2.0 |
| charset-normalizer | 3.4.4 | MIT |
| idna | 3.11 | BSD-3-Clause (`License-Expression`) |
| urllib3 | 2.5.0 | MIT (`License-Expression`) |
| packaging | 25.0 | Apache-2.0 OR BSD-style (per package classifiers/license files) |

## Practical redistribution checklist

- Keep this file in source and packaged distributions.
- Include the `third_party_licenses/` directory (or equivalent license texts)
  when redistributing bundled dependencies.
- Preserve copyright and license notices required by MIT/BSD/Apache/MPL.
- For Apache-2.0 packages, retain any required notices from their distributions.
- For MPL-2.0 packages (for example `certifi`), keep MPL terms and source
  availability obligations for MPL-covered files if you modify/re-distribute
  those files.

## Notes

- This notice covers dependency resolution from current `requirements.txt`.
- If dependencies change, update this file accordingly.
