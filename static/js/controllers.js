'use strict';

/* Controllers */

var mediaControllers = angular.module('mediaControllers', []);

mediaControllers.controller('ToolbarCtrl', ['$scope', '$http', '$interval',
  function ($scope, $http, $interval) {


    $scope.socket = io();
    $scope.socket.on('update', function(msg) {
      $scope.update();
    });

    // Update our github sources every 60 seconds. AngularJS re-draws the UI for us :-)
    var update_promise = $interval(function() {
      $http.get('http://api.github.com/repos/juju/juju/pulls').success(function (data) {
        var juju_pull_reqs = data;
        $scope.pull_reqs = [];
        juju_pull_reqs.every(function(currentValue, index, array){
          if(currentValue.user.login == "dooferlad") {
            $scope.pull_reqs.push(currentValue);
          }
          return true;
        })
      });
    }, 60 * 1000);

    $scope.$on('$destroy', function(){
      if (angular.isDefined(promise)) {
        $interval.cancel(promise);
        update_promise = undefined;
      }
    });

    $scope.update = function() {
      $http.get('/API/cards').success(function (data) {
        // We could fromat the data here so we can foreach over many data sources:
        // $scope.content.push({'heading': 'Cards', 'data': data});
        // This reduces flexibility though - can't handle cards differently from
        // bugs. Fine for name + url lists, not useful for other stuff.
        $scope.cards = data;
      });

      $http.get('/API/bugs').success(function (data) {
        $scope.my_bugs = data;
      });

      /*$http.get('/API/watched_bugs').success(function (data) {
        $scope.watched_bugs = data;
      });*/

      $http.get('/API/review_requests').success(function (data) {
        $scope.review_requests = data;
      });

      $http.get('/API/watched_reviews').success(function (data) {
        $scope.watched_reviews = data;
      });
    };

    /*$http.get('/API/cal').success(function (data) {
      //$scope.cal = data;
      $scope.cal = [];
      var now = Date.now()
      data.events.every(function(event){
        var t_diff = Date.parse(event.dtstart) - now;
        if(t_diff > 0 && t_diff < 1000*60*60*24*7) {
          var d = new Date();
          event.starttime = Date.parse(event.dtstart);
          d.setTime(event.starttime);
          event.dtstart = d.toString();
          d.setTime(Date.parse(event.dtend));
          event.dtend = d.toString();
          $scope.cal.push(event);
        }
        return true;
      });
    });*/

    $scope.card_filter = function(card) {
      return card.LaneTitle != "Merged";
    };

    $scope.bug_filter = function(bug) {
      return !(bug.status == "Fix Committed" ||
               bug.status == "Fix Released")
    };

    $scope.bug_url_submit = function(bug_url) {
      console.log(bug_url);
    };

    $scope.bugLabelImportance = function(bug) {
      switch(bug.importance) {
        case "Undecided":
          return "";
        case "Critical":
          return "label-danger";
        case "High":
          return "label-warning";
        case "Medium":
          return "label-success";
        case "Low":
          return "label-primary";
        case "Wishlist":
          return "label-info";
      }
      return "";
    };

    $scope.bugLabelStatus = function(bug) {
      switch(bug.status) {
        case "Invalid":
        case "Won't Fix":
          return "";
        case "New":
          return "label-danger";
        case "Triaged":
          return "label-warning";
        case "Fix Committed":
        case "Fix Released":
          return "label-success";
        case "Opinion":
          return "label-primary";
        case "In Progress":
          return "label-info";
      }
      return "";
    };

    $scope.cardLaneLabel = function(card) {
      switch(card.LaneTitle) {
        case "Done":
        case "Archive":
        case "Backlog":
          return "";
        case "Review":
          return "label-success";
        case "Investigating":
          return "label-primary";
        case "Coding":
          return "label-info";
      }
      return "label-danger";
    };
  }]);
