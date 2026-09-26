#!/usr/bin/env perl
# Converts the SIGNALduino protocol list from an RFFHEM checkout into the JSON file the
# integration reads:
#
#   git clone https://github.com/RFD-FHEM/RFFHEM.git
#   scripts/import_signalduino_protocols.pl RFFHEM \
#     > custom_components/cc1101duino/protocol/signalduino/protocols.json
#
# Code references (postDemodulation, method) become the bare function name, which
# protocol/signalduino/functions.py implements.
use strict;
use warnings;
use B;
use JSON::PP;
no warnings qw(once);

my $rffhem = shift // die "usage: $0 <path to RFFHEM checkout>\n";
require "$rffhem/lib/FHEM/Devices/SIGNALduino/SD_Protocols/Data.pm";

my %protocols = %FHEM::Devices::SIGNALduino::SD_Protocols::Data::protocols;
my %out;

for my $id (keys %protocols) {
  my %protocol;
  for my $key (keys %{ $protocols{$id} }) {
    my $value = $protocols{$id}{$key};
    if (ref $value eq 'CODE') {
      $value = B::svref_2object($value)->GV->NAME;
    } elsif (ref $value eq 'Regexp') {
      $value = "$value";
    }
    $protocol{$key} = $value;
  }
  $out{$id} = \%protocol;
}

my $commit = `git -C '$rffhem' rev-parse HEAD`;
chomp $commit;

print JSON::PP->new->canonical->pretty->encode({
  source   => 'https://github.com/RFD-FHEM/RFFHEM',
  commit   => $commit,
  version  => $FHEM::Devices::SIGNALduino::SD_Protocols::Data::VERSION,
  protocols => \%out,
});
