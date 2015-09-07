require "formula"

class AptStrict < Formula
  homepage "https://github.com/selivan/apt-strict"
  url "git@github.com:rivik/apt-strict.git", :using => :git
  version "0.5-10"

  depends_on "ansible"

  def install
        # no apt for max os x =), install ansible module only
        (share/'ansible/packaging').install 'apt_strict.py' => 'apt_strict'
  end
end
