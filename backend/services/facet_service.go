package services

import (
	"regexp"
	"strconv"
)

// Port of data_pipeline/llm_processor/facet_parser.py — the two must stay in
// lockstep so query-time facets match ingest-time facets.

type Facets struct {
	Seniority string // new_grad | intern | entry | senior | unknown
	Year      *int
}

var (
	seniorityRules = []struct {
		tag string
		re  *regexp.Regexp
	}{
		{"intern", regexp.MustCompile(`(?i)\bintern(ship)?\b`)},
		{"new_grad", regexp.MustCompile(`(?i)\b(new[\s\-]?grad(uate)?|graduate)\b`)},
		{"entry", regexp.MustCompile(`(?i)\b(junior|jr\.?|entry[\s\-]?level|associate)\b`)},
		{"senior", regexp.MustCompile(`(?i)\b(senior|sr\.?|lead|staff|principal)\b`)},
	}

	yearRe = regexp.MustCompile(`\b(20\d{2})\b`)
)

func ParseSeniority(title string) string {
	if title == "" {
		return "unknown"
	}
	for _, rule := range seniorityRules {
		if rule.re.MatchString(title) {
			return rule.tag
		}
	}
	return "unknown"
}

func ParseYear(title string) *int {
	if title == "" {
		return nil
	}
	m := yearRe.FindStringSubmatch(title)
	if len(m) < 2 {
		return nil
	}
	y, err := strconv.Atoi(m[1])
	if err != nil {
		return nil
	}
	return &y
}

func ParseFacets(title string) Facets {
	return Facets{
		Seniority: ParseSeniority(title),
		Year:      ParseYear(title),
	}
}
