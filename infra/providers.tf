provider "aws" {
  region = var.region

  # Every resource carries these. Project is what makes a Cost Explorer sweep
  # grouped by tag answer "is this mine?"; ManagedBy marks anything hand-clicked
  # into the account as the exception it should be.
  default_tags {
    tags = {
      Project   = "carpool"
      ManagedBy = "terraform"
    }
  }
}
