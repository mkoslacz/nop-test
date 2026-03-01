from __future__ import annotations

from src.checkers.base import BaseChecker
from src.models.findings import AuditResult, CheckerType


class FormsChecker(BaseChecker):
    """Tests search form functionality on the migrated page."""

    checker_type = CheckerType.FORMS

    async def run(self) -> AuditResult:
        results: list[dict] = []
        results.append(await self._test_search_form_presence())
        results.append(await self._test_autocomplete())
        results.append(await self._test_date_picker())
        results.append(await self._test_guest_selector())
        results.append(await self._test_form_submission())

        passed = sum(1 for r in results if r.get("passed", False))
        return self._build_result(
            raw_data={"test_results": results},
            summary=f"Form tests: {passed}/{len(results)} passed",
        )

    async def _test_search_form_presence(self) -> dict:
        """Check that the search form exists with all expected fields."""
        page = await self.browser.new_page(self.settings.migrated_url)
        result = await page.evaluate("""() => {
            const form = document.querySelector(
                'form, .search-form, .search-box, [data-testid*="search"]'
            );
            if (!form) return { found: false };

            const inputs = [...form.querySelectorAll('input')];
            const buttons = [...form.querySelectorAll('button[type="submit"], button:not([type]),.search-button')];

            return {
                found: true,
                input_count: inputs.length,
                input_types: inputs.map(i => ({
                    type: i.type,
                    name: i.name || i.id || '',
                    placeholder: i.placeholder || '',
                })),
                has_submit_button: buttons.length > 0,
                button_text: buttons.map(b => b.textContent?.trim() || ''),
            };
        }""")
        await page.context.close()
        return {
            "test": "search_form_presence",
            "passed": result.get("found", False),
            "details": result,
        }

    async def _test_autocomplete(self) -> dict:
        """Type in the location field and check if autocomplete suggestions appear."""
        page = await self.browser.new_page(self.settings.migrated_url)
        try:
            # Find location input
            location_input = page.locator(
                'input[placeholder*="miasto"], input[placeholder*="city"], '
                'input[placeholder*="np."], input[placeholder*="Dokąd"], '
                'input[name*="location"], input[name*="destination"], '
                'input[type="search"], .search-input input'
            ).first

            if not await location_input.is_visible(timeout=5000):
                return {"test": "autocomplete", "passed": False, "error": "Location input not found"}

            await location_input.click()
            await location_input.fill("Zakopane")
            await page.wait_for_timeout(2000)

            # Check for autocomplete dropdown
            suggestions = await page.evaluate("""() => {
                const candidates = document.querySelectorAll(
                    '.autocomplete-results, .suggestions, [role="listbox"], ' +
                    '.search-suggestions, .dropdown-menu, [class*="suggest"], ' +
                    '[class*="autocomplete"], ul[class*="result"]'
                );
                for (const el of candidates) {
                    if (el.offsetParent !== null && el.children.length > 0) {
                        return {
                            found: true,
                            count: el.children.length,
                            items: [...el.children]
                                .slice(0, 5)
                                .map(c => c.textContent?.trim().substring(0, 100) || ''),
                        };
                    }
                }
                return { found: false, count: 0, items: [] };
            }""")

            return {
                "test": "autocomplete",
                "passed": suggestions.get("found", False),
                "details": suggestions,
            }
        except Exception as e:
            return {"test": "autocomplete", "passed": False, "error": str(e)}
        finally:
            await page.context.close()

    async def _test_date_picker(self) -> dict:
        """Click the date field and check if a calendar/date picker appears."""
        page = await self.browser.new_page(self.settings.migrated_url)
        try:
            date_input = page.locator(
                'input[type="date"], input[name*="date"], input[name*="arrival"], '
                'input[name*="checkin"], input[placeholder*="przyjazd"], '
                'input[placeholder*="data"], .date-picker input, '
                '[data-testid*="date"], [class*="date-input"]'
            ).first

            if not await date_input.is_visible(timeout=5000):
                return {"test": "date_picker", "passed": False, "error": "Date input not found"}

            await date_input.click()
            await page.wait_for_timeout(1500)

            calendar_visible = await page.evaluate("""() => {
                const calendars = document.querySelectorAll(
                    '.calendar, .datepicker, [role="dialog"], [class*="calendar"], ' +
                    '[class*="datepicker"], .picker, .date-range-picker'
                );
                for (const el of calendars) {
                    if (el.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            }""")

            return {"test": "date_picker", "passed": calendar_visible}
        except Exception as e:
            return {"test": "date_picker", "passed": False, "error": str(e)}
        finally:
            await page.context.close()

    async def _test_guest_selector(self) -> dict:
        """Test guest/room selector widget."""
        page = await self.browser.new_page(self.settings.migrated_url)
        try:
            guest_trigger = page.locator(
                '[class*="guest"], [class*="person"], [data-testid*="guest"], '
                '[class*="occupancy"], button:has-text("osob"), button:has-text("gości"), '
                'button:has-text("dorosł")'
            ).first

            if not await guest_trigger.is_visible(timeout=5000):
                return {"test": "guest_selector", "passed": False, "error": "Guest selector not found"}

            await guest_trigger.click()
            await page.wait_for_timeout(1000)

            dropdown_visible = await page.evaluate("""() => {
                const dropdowns = document.querySelectorAll(
                    '[class*="guest"] [class*="dropdown"], [class*="occupancy-dropdown"], ' +
                    '[class*="guest-picker"], [class*="person-select"]'
                );
                for (const el of dropdowns) {
                    if (el.offsetParent !== null) return true;
                }
                // Also check for +/- buttons that might have appeared
                const buttons = document.querySelectorAll(
                    'button:has-text("+"), button:has-text("-"), ' +
                    '[class*="increment"], [class*="decrement"]'
                );
                return buttons.length >= 2;
            }""")

            return {"test": "guest_selector", "passed": dropdown_visible}
        except Exception as e:
            return {"test": "guest_selector", "passed": False, "error": str(e)}
        finally:
            await page.context.close()

    async def _test_form_submission(self) -> dict:
        """Test that form submission navigates to correct URL (noclegi.pl search results)."""
        page = await self.browser.new_page(self.settings.migrated_url)
        try:
            # Fill location
            location_input = page.locator(
                'input[placeholder*="miasto"], input[placeholder*="city"], '
                'input[placeholder*="np."], input[placeholder*="Dokąd"], '
                'input[type="search"], .search-input input'
            ).first

            if not await location_input.is_visible(timeout=5000):
                return {"test": "form_submission", "passed": False, "error": "Location input not found"}

            await location_input.fill("Zakopane")
            await page.wait_for_timeout(1500)

            # Try to click first autocomplete result if available
            try:
                first_suggestion = page.locator(
                    '.autocomplete-results li, .suggestions li, '
                    '[role="option"], [class*="suggest"] li'
                ).first
                if await first_suggestion.is_visible(timeout=2000):
                    await first_suggestion.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            # Click submit
            submit_btn = page.locator(
                'button[type="submit"], .search-button, '
                'button:has-text("Szukaj"), button:has-text("Znajdź"), '
                'button:has-text("Search")'
            ).first

            if not await submit_btn.is_visible(timeout=3000):
                return {"test": "form_submission", "passed": False, "error": "Submit button not found"}

            await submit_btn.click()
            await page.wait_for_load_state("networkidle", timeout=10000)

            final_url = page.url
            # Check that the form submits to noclegi.pl (not nop-go)
            is_correct_domain = "noclegi.pl" in final_url and "nop-go" not in final_url

            return {
                "test": "form_submission",
                "passed": is_correct_domain,
                "final_url": final_url,
                "expected_domain": "noclegi.pl",
            }
        except Exception as e:
            return {"test": "form_submission", "passed": False, "error": str(e)}
        finally:
            await page.context.close()
