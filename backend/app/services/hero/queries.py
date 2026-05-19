"""GraphQL-Strings für HERO. Minimaler Satz — nur was das Planung-Tool braucht."""

COMPANY_PARTNERS = """
query CompanyPartners {
  user {
    partner {
      id
      full_name
      company {
        company_branches {
          partners {
            id
            full_name
            user {
              id
              email
            }
          }
        }
      }
    }
  }
}
"""

TRACKING_TIMES_CATEGORIES = """
{ tracking_times_categories { id name is_working_time } }
"""

# Tracking-Time create/update — id null = create, id gesetzt = update.
UPDATE_TRACKING_TIME = """
mutation UpdateTrackingTime($tt: Employees_TrackingTimeInput!) {
  update_tracking_time(tracking_time: $tt) {
    id
    uuid
    partner_id
    project_match_id
    start
    end
    duration_in_seconds
    status_code
  }
}
"""

# Globale Suche nach ProjectMatch — hilft beim Mapping Planung-Tool-Projekt
# ↔ HERO-Projekt anhand des Namens/Projekt-Nr.
GLOBAL_SEARCH_PROJECTS = """
query SearchProjects($term: String!, $first: Int!) {
  global_search(term: $term, category: project_matches, first: $first) {
    ... on ProjectMatch {
      id name project_nr
      measure { name short }
      current_project_match_status { name }
      customer { full_name }
    }
  }
}
"""
