from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from backend.compatibility_engine.nakshatra_matching import NakshatraMatcher, normalize_nakshatra
from backend.models.schemas import PersonDetails
from backend.swiss_engine.horoscope_generator import HoroscopeGenerator
from backend.utils.constants import REQUIRED_EXCEL_COLUMNS
from backend.utils.excel_io import write_excel


def _age_from_dob(value: object, today: date) -> int | None:
    if isinstance(value, datetime):
        born = value.date()
    elif isinstance(value, date):
        born = value
    else:
        text = str(value).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            born = datetime.strptime(text, "%Y-%m-%d").date()
        else:
            dob = pd.to_datetime(value, errors="coerce", dayfirst=True)
            if pd.isna(dob):
                return None
            born = dob.date()
    age = today.year - born.year
    return age - ((today.month, today.day) < (born.month, born.day))

def _has_degree_or_higher(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False

    below_degree_patterns = (
        r"\bssc\b",
        r"\bsslc\b",
        r"\b10th\b",
        r"\btenth\b",
        r"\binter\b",
        r"\bintermediate\b",
        r"\b12th\b",
        r"\btwelfth\b",
        r"\bplus\s*2\b",
        r"\b\+2\b",
        r"\bdiploma\b",
        r"\biti\b",
    )
    degree_patterns = (
        r"\bdegree\b",
        r"\bgraduate\b",
        r"\bgraduation\b",
        r"\bunder\s*graduate\b",
        r"\bundergraduate\b",
        r"\bug\b",
        r"\bbachelor",
        r"\bmaster",
        r"\bpg\b",
        r"\bpost\s*graduate\b",
        r"\bpostgraduate\b",
        r"\bdoctorate\b",
        r"\bph\.?d\b",
        r"\bphd\b",
        r"\bm\.?phil\b",
        r"\bd\.?phil\b",
        r"\bb\.?tech\b",
        r"\bm\.?tech\b",
        r"\bbachelor\sof\stechnology\b",
        r"\bmaster\sof\stechnology\b",
        r"\bb\.?e\b",
        r"\bm\.?e\b",
        r"\bbachelor\sof\sengineering\b",
        r"\bmaster\sof\sengineering\b",
        r"\bb\.?sc\b",
        r"\bm\.?sc\b",
        r"\bbachelor\sof\sscience\b",
        r"\bmaster\sof\sscience\b",
        r"\bb\.?com\b",
        r"\bm\.?com\b",
        r"\bbachelor\sof\scommerce\b",
        r"\bmaster\sof\scommerce\b",
        r"\bb\.?a\b",
        r"\bm\.?a\b",
        r"\bbachelor\sof\sarts\b",
        r"\bmaster\sof\sarts\b",
        r"\bb\.?b\.?a\b",
        r"\bm\.?b\.?a\b",
        r"\bbachelor\sof\sbusiness\s*administration\b",
        r"\bmaster\sof\sbusiness\s*administration\b",
        r"\bb\.?c\.?a\b",
        r"\bm\.?c\.?a\b",
        r"\bbachelor\sof\scomputer\s*applications?\b",
        r"\bmaster\sof\scomputer\s*applications?\b",
        r"\bb\.?ed\b",
        r"\bm\.?ed\b",
        r"\bbachelor\sof\seducation\b",
        r"\bmaster\sof\seducation\b",
        r"\bb\.?pharm\b",
        r"\bm\.?pharm\b",
        r"\bbachelor\sof\spharmacy\b",
        r"\bmaster\sof\spharmacy\b",
        r"\bb\.?arch\b",
        r"\bm\.?arch\b",
        r"\bbachelor\sof\sarchitecture\b",
        r"\bmaster\sof\sarchitecture\b",
        r"\bb\.?des\b",
        r"\bm\.?des\b",
        r"\bbachelor\sof\sdesign\b",
        r"\bmaster\sof\sdesign\b",
        r"\bb\.?voc\b",
        r"\bm\.?voc\b",
        r"\bmbbs\b",
        r"\bmd\b",
        r"\bms\b",
        r"\bbds\b",
        r"\bmds\b",
        r"\bbams\b",
        r"\bbhms\b",
        r"\bums\b",
        r"\bbnys\b",
        r"\bbpt\b",
        r"\bmpt\b",
        r"\bb\.?sc\s*nursing\b",
        r"\bgnm\b",
        r"\bllb\b",
        r"\bllm\b",
        r"\bb\.?l\b",
        r"\bm\.?l\b",
        r"\bca\b",
        r"\bcma\b",
        r"\bcs\b",
        r"\bacca\b",
        r"\bcfa\b",
    )

    has_degree = any(re.search(pattern, text) for pattern in degree_patterns)
    if has_degree:
        return True
    return False

class FilteringService:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.nakshatra = NakshatraMatcher()
        self.horoscope = HoroscopeGenerator()
        self.last_rejections = pd.DataFrame()

    def filter_users(self, person: PersonDetails, users: pd.DataFrame) -> pd.DataFrame:
        filtered, rejected = self.filter_users_with_rejections(person, users)
        self.last_rejections = rejected
        return filtered.reset_index(drop=True)

    def filter_users_with_rejections(self, person: PersonDetails, users: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        users = self._normalize_user_columns(users)
        missing = [column for column in REQUIRED_EXCEL_COLUMNS if column not in users.columns]
        if missing:
            raise ValueError(f"Excel file is missing required columns: {', '.join(missing)}")

        df = users.copy()
        today = date.today()
        calculated_ages = df["DOB"].map(lambda value: _age_from_dob(value, today))
        if "Age" not in df.columns:
            df["Age"] = calculated_ages
        else:
            uploaded_ages = pd.to_numeric(df["Age"], errors="coerce")
            df["Age"] = uploaded_ages.fillna(calculated_ages)

        if "Gender" not in df.columns:
            df["Gender"] = "Female"
        else:
            df["Gender"] = df["Gender"].fillna("Female")

        age_mask = pd.to_numeric(df["Age"], errors="coerce").le(person.age)
        education_mask = df["Education"].map(_has_degree_or_higher)
        boy_star = self._source_nakshatra(person)
        reports = pd.Series(
            self.nakshatra.score_pairs([(boy_star, value) for value in df["Star"].tolist()]),
            index=df.index,
        )
        girl_nakshatra = reports.map(lambda report: report.get("girl_nakshatra"))
        df["Nakshathra"] = girl_nakshatra.fillna(df["Star"])
        df["Gothram"] = df["Gotram"]

        nakshatra_reasons = reports.map(lambda report: report.get("reason") if report.get("rejected") else None)
        df["Compatibility Warning"] = nakshatra_reasons
        passed_mask = age_mask & education_mask
        filtered = df[passed_mask].reset_index(drop=True)
        rejected = df[~passed_mask].copy()
        rejected["Rejection Reason"] = [
            self._rejection_reason(
                bool(age_mask.loc[index]),
                bool(education_mask.loc[index]),
            )
            for index in rejected.index
        ]
        return filtered, rejected.reset_index(drop=True)

    @staticmethod
    def _normalize_user_columns(users: pd.DataFrame) -> pd.DataFrame:
        df = users.copy()
        if "Star" not in df.columns:
            for column in ("Nakshathra", "Nakshatra"):
                if column in df.columns:
                    df["Star"] = df[column]
                    break
        if "Gotram" not in df.columns and "Gothram" in df.columns:
            df["Gotram"] = df["Gothram"]
        return df

    def export_filtered_users(self, filtered: pd.DataFrame) -> Path:
        return write_excel(filtered, self.output_dir / "filtered_users.xlsx")

    def export_rejected_users(self, rejected: pd.DataFrame) -> Path:
        return write_excel(rejected, self.output_dir / "rejected_users.xlsx")

    def _source_nakshatra(self, person: PersonDetails) -> str:
        try:
            horoscope = self.horoscope.generate(person, include_timing=False)
            return str(horoscope["moon_nakshatra"])
        except Exception:
            normalized = normalize_nakshatra(person.star)
            if normalized.name:
                return normalized.name
            raise

    @staticmethod
    def _rejection_reason(age_passed: bool, education_passed: bool) -> str:
        reasons = []
        if not age_passed:
            reasons.append("Candidate age is greater than source age")
        if not education_passed:
            reasons.append("Candidate study is below degree level")
        return "; ".join(reasons) if reasons else "Filtered by compatibility rules"
